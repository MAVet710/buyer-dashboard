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
from .privacy import pseudonym, source_identity
from .store import append_events, collect_privileged_audits, detect, insert_for, open_incident

logger = logging.getLogger(__name__)
KINDS = frozenset(("login_failure", "login_success", "scope_denial"))


class SecurityMonitor:
    def __init__(self, engine, settings, capacity=1024):
        self.engine, self.settings = engine, settings
        self.enabled = bool(settings.security_monitor_enabled)
        self.configured = len(settings.security_hmac_secret) >= 32
        self.queue = queue.Queue(maxsize=capacity)
        self.pending = []
        self.identifier = "worker:" + str(uuid4())
        self.stop_event = asyncio.Event()
        self.task = None
        self.started_at = time.time()
        self.last_success = 0.0
        self.failures = 0
        self.dropped = 0
        self.last_warning = 0.0
        self.saturated = False
        self.last_tick_failed = False
        self.reported_dropped = 0
        self.reported_failures = 0
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
                actor_id=str(actor_id)[:36], organization_id=str(organization_id)[:36],
                route=str(route)[:200], request_id=str(uuid4()), audit_id="")
            self.queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self.dropped += 1
        except Exception:
            with self._lock:
                self.failures += 1

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
        return dict(state=state, last_success=self.last_success or None,
            queued=self.queue.qsize() + len(self.pending), dropped=self.dropped,
            failures=self.failures, saturated=self.saturated,
            notifications="not_connected", response_mode="alert_only",
            coverage={"username_login": "instrumented", "scope_denials": "instrumented",
                      "privileged_changes": "canonical_audit_poll",
                      "supabase_direct_auth": "not_connected", "cloudflare": "not_connected",
                      "defender": "not_connected", "external_heartbeat": "not_connected"})

    def tick(self, now=None):
        if not self.enabled or not self.configured:
            return
        now = time.time() if now is None else now
        batch = self.pending
        self.pending = []
        while len(batch) < 64:
            try:
                batch.append(self.queue.get_nowait())
            except queue.Empty:
                break
        try:
            with Session(self.engine) as session, session.begin():
                if self.engine.dialect.name == "postgresql":
                    session.execute(text("SET LOCAL statement_timeout = '2500ms'"))
                append_events(session, batch)
                saturated = collect_privileged_audits(session, self.settings.security_hmac_secret, now)
                saturated = detect(session, now) or saturated
                if self.dropped > self.reported_dropped or self.failures > self.reported_failures or saturated:
                    open_incident(session, "monitoring_degraded", self.identifier, max(1, self.dropped + self.failures),
                        now, {"dropped": self.dropped, "failures": self.failures, "saturated": saturated}, "warning")
                values = dict(id=self.identifier, checked_at=now, status="degraded" if saturated else "observing",
                              dropped=self.dropped, failures=self.failures)
                session.execute(insert_for(session, SecurityMonitorState).values(**values)
                    .on_conflict_do_update(index_elements=["id"], set_={k:v for k,v in values.items() if k != "id"}))
            self.saturated = saturated
            self.last_success = now
            self.last_tick_failed = False
            self.reported_dropped = self.dropped
            self.reported_failures = self.failures
        except Exception:
            self.last_tick_failed = True
            self.pending = batch
            self.failures += 1
            if now - self.last_warning >= 60:
                logger.warning("SECURITY_MONITOR_DEGRADED: inspect protected monitoring health")
                self.last_warning = now

    async def run(self):
        while not self.stop_event.is_set():
            await asyncio.to_thread(self.tick)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=10)
            except TimeoutError:
                pass
        await asyncio.to_thread(self.tick)

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
