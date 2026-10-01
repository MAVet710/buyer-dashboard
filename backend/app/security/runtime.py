"""Bounded observer. Authentication never depends on monitoring availability."""
import asyncio
import logging
import queue
import threading
import time
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import SecurityMonitorState
from .notifications import SecurityNotifier
from .retention import maintain, available_capacity
from .privacy import pseudonym, source_identity
from .store import (append_events, collect_privileged_audits, detect, insert_for,
                    open_incident, recover_monitoring_incidents, recover_rule_incidents)
from .perimeter import PerimeterCollector
from .guard import evaluate_guard, local_ai_review

logger = logging.getLogger(__name__)
KINDS = frozenset(("login_failure", "login_success", "scope_denial", "honey_touch"))


def _error_category(exc):
    value = str(exc).casefold()
    if "getaddrinfo" in value or "resolve host" in value:
        return "database_dns_failure"
    if "timeout" in value:
        return "database_connection_timeout"
    if "operational" in type(exc).__name__.casefold():
        return "database_operational_error"
    return "monitor_processing_error"


class SecurityMonitor:
    def __init__(self, engine, settings, capacity=1024):
        self.engine, self.settings = engine, settings
        self.notifier = SecurityNotifier(engine, settings)
        self.enabled = bool(settings.security_monitor_enabled)
        self.configured = len(settings.security_hmac_secret) >= 32
        self.queue = queue.Queue(maxsize=capacity)
        self.pending = []
        self.identifier = "worker:" + str(uuid4())
        self.stop_event = asyncio.Event()
        self.task = None
        self.started_at = time.time()
        self.last_success = 0.0
        self.last_maintenance = 0.0
        self.failures = 0
        self.dropped = 0
        self.last_warning = 0.0
        self.saturated = False
        self.last_tick_failed = False
        self.reported_dropped = 0
        self.reported_failures = 0
        self.last_ai_review = 0.0
        self.ai_task = None
        self.ai_review_state = None
        self.last_error_category = ""
        self.last_error_at = 0.0
        self.clean_cycles = 0
        self.perimeter = PerimeterCollector(engine, settings)
        self._lock = threading.Lock()

    def emit(self, request, kind, subject, actor_id="", organization_id=""):
        if not self.enabled or not self.configured or kind not in KINDS:
            return
        try:
            key = self.settings.security_hmac_secret
            route = getattr(request.scope.get("route"), "path", "unmatched")
            event = dict(id=str(uuid4()), occurred_at=time.time(), kind=kind,
                subject_key=pseudonym(key, "subject", str(subject)),
                source_key=pseudonym(key, "source", source_identity(request, self.settings)),
                actor_id=str(actor_id)[:64], organization_id=str(organization_id)[:36],
                route=str(route)[:200], request_id=str(uuid4()), audit_id="")
            self.queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self.dropped += 1
        except Exception:
            with self._lock:
                self.failures += 1
                self.last_error_category = "event_observation_error"
                self.last_error_at = time.time()
                self.clean_cycles = 0

    def health(self):
        now = time.time()
        if not self.enabled:
            state = "disabled"
        elif not self.configured:
            state = "configuration_required"
        elif not self.last_success:
            state = "starting" if now - self.started_at < 30 else "degraded"
        elif now - self.last_success > 30 or self.saturated or self.pending or self.last_tick_failed:
            state = "degraded"
        else:
            state = "observing"
        perimeter = self.perimeter.public()
        def source_status(name, fallback):
            return perimeter.get(name, {}).get("status", fallback)
        return dict(
            state=state, last_success=self.last_success or None,
            queued=self.queue.qsize() + len(self.pending), dropped=self.dropped,
            failures=self.failures, saturated=self.saturated,
            new_failures=max(0, self.failures - self.reported_failures),
            new_dropped=max(0, self.dropped - self.reported_dropped),
            last_error_category=self.last_error_category or None,
            last_error_at=self.last_error_at or None,
            clean_cycles=self.clean_cycles,
            notifications=self.notifier.state, notification_detail=self.notifier.health(),
            response_mode="defensive_guard",
            coverage={
                "username_login": "instrumented",
                "scope_denials": "instrumented",
                "privileged_changes": "canonical_audit_poll",
                "supabase_direct_auth": source_status("supabase:auth_audit", "starting"),
                "cloudflare": source_status("cloudflare:tunnel", "starting"),
                "defender": source_status("windows:defender", "starting"),
                "external_heartbeat": "not_connected",
            },
            perimeter=perimeter,
        )

    def tick(self, now=None):
        if not self.enabled or not self.configured:
            return
        now = time.time() if now is None else float(now)
        batch = self.pending
        self.pending = []
        while len(batch) < 64:
            try:
                batch.append(self.queue.get_nowait())
            except queue.Empty:
                break
        prior_new_failures = max(0, self.failures - self.reported_failures)
        prior_new_dropped = max(0, self.dropped - self.reported_dropped)
        try:
            with Session(self.engine) as session, session.begin():
                if self.engine.dialect.name == "postgresql":
                    session.execute(text("SET LOCAL statement_timeout = '2500ms'"))
                if now - self.last_maintenance >= 60:
                    maintain(session, now)
                capacity = available_capacity(session, self.settings.security_event_capacity)
                lost = max(0, len(batch) - capacity)
                append_events(session, batch[:capacity])
                saturated = lost > 0 or capacity <= len(batch) + 200
                if capacity > len(batch) + 200:
                    saturated = collect_privileged_audits(
                        session, self.settings.security_hmac_secret, now
                    ) or saturated
                saturated = detect(session, now) or saturated
                state = evaluate_guard(session, now)
                new_failures = prior_new_failures
                new_dropped = prior_new_dropped + lost
                issue = bool(new_failures or new_dropped or saturated)
                next_clean_cycles = 0 if issue else self.clean_cycles + 1
                mail_state = self.notifier.state
                mail_problem = bool(
                    self.settings.security_notifications_enabled
                    and mail_state in {
                        "mail_credentials_unavailable", "mail_credentials_required",
                        "sender_required", "attention_required", "storage_unavailable",
                    }
                )
                if mail_problem:
                    open_incident(
                        session, "alert_delivery_degraded", mail_state, 1, now,
                        {"notification_state": mail_state,
                         "automatic_retry": False,
                         "provider_delivery_confirmed": False},
                        "warning",
                    )
                elif self.settings.security_notifications_enabled and mail_state == "ready":
                    recover_rule_incidents(
                        session, "alert_delivery_degraded", now,
                        {"notification_state": "ready", "recovered_at": now},
                    )
                if issue:
                    open_incident(
                        session, "monitoring_degraded", self.identifier,
                        max(1, new_failures + new_dropped),
                        now,
                        {
                            "new_failures": new_failures,
                            "new_dropped": new_dropped,
                            "lifetime_failures": self.failures,
                            "lifetime_dropped": self.dropped + lost,
                            "saturated": saturated,
                            "last_error_category": self.last_error_category or "",
                            "last_error_at": self.last_error_at or 0,
                        },
                        "warning",
                    )
                else:
                    recover_monitoring_incidents(
                        session, now, self.identifier, self.failures,
                        self.dropped + lost, next_clean_cycles,
                    )
                values = dict(
                    id=self.identifier, checked_at=now,
                    status="degraded" if issue else "observing",
                    dropped=self.dropped + lost, failures=self.failures,
                    last_error_category=self.last_error_category,
                    last_error_at=self.last_error_at,
                    clean_cycles=next_clean_cycles,
                )
                session.execute(
                    insert_for(session, SecurityMonitorState).values(**values)
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={k: v for k, v in values.items() if k != "id"},
                    )
                )
            self.saturated = saturated
            self.dropped += lost
            self.last_maintenance = now if now - self.last_maintenance >= 60 else self.last_maintenance
            self.last_success = now
            self.last_tick_failed = False
            self.clean_cycles = next_clean_cycles
            self.reported_dropped = self.dropped
            self.reported_failures = self.failures
            # Perimeter source failures are isolated from core observation health.
            self.perimeter.tick(now)
            if now - self.last_ai_review >= 60 and state.get("risk_score", 0) >= 40:
                # Hand off only the bounded guard state. Local model latency must
                # never delay observer heartbeats or notifier processing.
                self.ai_review_state = dict(state)
        except Exception as exc:
            self.last_tick_failed = True
            self.pending = batch
            self.failures += 1
            self.clean_cycles = 0
            self.last_error_category = _error_category(exc)
            self.last_error_at = now
            if now - self.last_warning >= 60:
                logger.warning(
                    "SECURITY_MONITOR_DEGRADED category=%s",
                    self.last_error_category,
                )
                self.last_warning = now

    def _schedule_ai_review(self):
        if self.ai_task is not None and self.ai_task.done():
            try:
                self.ai_task.result()
            except Exception:
                pass
            self.ai_task = None
        state = self.ai_review_state
        if state is None or self.ai_task is not None:
            return
        now = time.time()
        if now - self.last_ai_review < 60:
            return
        self.ai_review_state = None
        self.last_ai_review = now
        self.ai_task = asyncio.create_task(
            asyncio.to_thread(local_ai_review, self.engine, self.settings, state),
            name="doobielogic-security-local-ai",
        )

    async def run(self):
        while not self.stop_event.is_set():
            await asyncio.to_thread(self.tick)
            self._schedule_ai_review()
            await asyncio.to_thread(self.notifier.tick)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=10)
            except TimeoutError:
                pass
        await asyncio.to_thread(self.tick)
        self._schedule_ai_review()
        if self.ai_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self.ai_task), timeout=50)
            except (TimeoutError, asyncio.CancelledError):
                pass

    def start(self):
        if self.enabled and self.configured and self.task is None:
            self.task = asyncio.create_task(self.run(), name="doobielogic-security-observer")

    async def stop(self):
        self.stop_event.set()
        if self.task is not None:
            await self.task
            self.task = None


def observe(request, kind, subject, actor_id="", organization_id=""):
    # Trusted server call sites only; there is no public event-ingestion endpoint.
    if request is None:
        return
    try:
        monitor = getattr(request.app.state, "security_monitor", None)
        if monitor is not None:
            monitor.emit(request, kind, subject, actor_id, organization_id)
    except Exception:
        logger.warning("SECURITY_OBSERVATION_UNAVAILABLE")
