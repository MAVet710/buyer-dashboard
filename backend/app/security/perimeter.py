"""Best-effort perimeter collectors. Source failure never disables core authentication monitoring."""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .models import SecurityEvent, SecuritySourceState
from .privacy import pseudonym
from .store import append_events, insert_for, open_incident

SOURCE_INTERVAL = 60
MAX_EVENTS = 200
DEFENDER_LOG = "Microsoft-Windows-Windows Defender/Operational"
DEFENDER_HIGH = frozenset({1116, 1118, 1119, 5001})
DEFENDER_REVIEW = frozenset({1121, 5007})


def _category(exc: Exception) -> str:
    name = type(exc).__name__.casefold()
    value = str(exc).casefold()
    if "permission" in value or "access is denied" in value:
        return "permission_denied"
    if "timeout" in value:
        return "timeout"
    if "not found" in value or "does not exist" in value:
        return "source_unavailable"
    if "operational" in name or "connection" in value:
        return "connection_error"
    return "collector_error"


def _state(session, source_id: str):
    return session.get(SecuritySourceState, source_id)


def _upsert_state(session, *, source_id: str, now: float, status: str, cursor: str = "",
                  failures: int = 0, last_error_category: str = "", last_event_at: float = 0,
                  detail: dict | None = None):
    values = dict(id=source_id, checked_at=now, status=status, cursor=cursor[:160],
                  failures=max(0, int(failures)), last_error_category=last_error_category[:64],
                  last_event_at=float(last_event_at or 0),
                  detail_json=json.dumps(detail or {}, sort_keys=True, separators=(",", ":")))
    session.execute(insert_for(session, SecuritySourceState).values(**values).on_conflict_do_update(
        index_elements=["id"], set_={k: v for k, v in values.items() if k != "id"}))
    return values


def _defender_command():
    # No user-controlled shell material. We deliberately collect metadata only, never event messages.
    return (
        "$ErrorActionPreference='Stop';"
        f"$log='{DEFENDER_LOG}';"
        "$events=@(Get-WinEvent -FilterHashtable @{LogName=$log;StartTime=(Get-Date).AddMinutes(-15)} "
        "-ErrorAction SilentlyContinue | Select-Object -First 300 | ForEach-Object { "
        "[ordered]@{TimeCreated=$_.TimeCreated.ToUniversalTime().ToString('o');Id=$_.Id;RecordId=$_.RecordId;LevelDisplayName=$_.LevelDisplayName} });"
        "$events | ConvertTo-Json -Compress"
    )


def collect_defender(engine, secret: str, now: float):
    source_id = "windows:defender"
    with Session(engine) as session:
        prior = _state(session, source_id)
        prior_cursor = int(prior.cursor) if prior and str(prior.cursor).isdigit() else 0
        prior_failures = int(prior.failures or 0) if prior else 0
    if os.name != "nt":
        with Session(engine) as session, session.begin():
            return _upsert_state(session, source_id=source_id, now=now, status="not_available",
                                 cursor=str(prior_cursor), failures=prior_failures,
                                 detail={"platform": os.name, "security_events": False})
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _defender_command()],
            capture_output=True, text=True, timeout=8, check=True,
        )
        raw = result.stdout.strip()
        rows = [] if not raw or raw == "null" else json.loads(raw)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or len(rows) > 300:
            raise RuntimeError("invalid_defender_response")
        events, highest, last_event_at = [], prior_cursor, 0.0
        alert_counts: dict[int, int] = {}
        for row in rows:
            record_id = int(row.get("RecordId") or 0)
            event_id = int(row.get("Id") or 0)
            if record_id <= prior_cursor:
                continue
            highest = max(highest, record_id)
            if event_id not in DEFENDER_HIGH | DEFENDER_REVIEW:
                continue
            stamp = str(row.get("TimeCreated") or "")
            try:
                observed = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
            except ValueError:
                observed = now
            last_event_at = max(last_event_at, observed)
            identity = str(uuid5(NAMESPACE_URL, f"doobielogic:defender:{record_id}"))
            kind = "defender_alert" if event_id in DEFENDER_HIGH else "defender_change"
            events.append(dict(
                id=identity, occurred_at=observed, kind=kind,
                subject_key=pseudonym(secret, "defender-record", str(record_id)),
                source_key=pseudonym(secret, "host", "local-windows-host"),
                actor_id="", organization_id="", route=f"windows_defender:{event_id}",
                request_id="", audit_id=identity,
            ))
            alert_counts[event_id] = alert_counts.get(event_id, 0) + 1
        with Session(engine) as session, session.begin():
            append_events(session, events[:MAX_EVENTS])
            for event_id, count in alert_counts.items():
                if event_id in DEFENDER_HIGH:
                    open_incident(session, "defender_alert", f"event:{event_id}", count, now,
                                  {"event_id": event_id, "source": "windows_defender",
                                   "new_events": count, "message_collected": False}, "high")
            return _upsert_state(session, source_id=source_id, now=now, status="observing",
                                 cursor=str(highest), failures=prior_failures,
                                 last_event_at=last_event_at,
                                 detail={"security_events": True, "new_events": len(events),
                                         "message_collected": False})
    except Exception as exc:
        category = _category(exc)
        with Session(engine) as session, session.begin():
            return _upsert_state(session, source_id=source_id, now=now, status="degraded",
                                 cursor=str(prior_cursor), failures=prior_failures + 1,
                                 last_error_category=category,
                                 detail={"security_events": True, "error_category": category})


def collect_supabase_auth(engine, secret: str, now: float):
    source_id = "supabase:auth_audit"
    with Session(engine) as session:
        prior = _state(session, source_id)
        prior_failures = int(prior.failures or 0) if prior else 0
        since = max(now - 600, float(prior.last_event_at or 0) - 60) if prior else now - 600
    if engine.dialect.name != "postgresql":
        with Session(engine) as session, session.begin():
            return _upsert_state(session, source_id=source_id, now=now, status="not_available",
                                 failures=prior_failures, detail={"security_events": False})
    try:
        with Session(engine) as session:
            exists = session.scalar(text("SELECT to_regclass('auth.audit_log_entries')"))
            if not exists:
                raise RuntimeError("source_unavailable")
            rows = session.execute(text("""
                SELECT id::text, EXTRACT(EPOCH FROM created_at), COALESCE(payload->>'action',''),
                       COALESCE(ip_address,'')
                FROM auth.audit_log_entries
                WHERE created_at >= to_timestamp(:since)
                ORDER BY created_at, id
                LIMIT 201
            """), {"since": since}).all()
        if len(rows) > MAX_EVENTS:
            rows = rows[:MAX_EVENTS]
            status = "bounded"
        else:
            status = "observing"
        events, last_event_at = [], float(prior.last_event_at or 0) if prior else 0.0
        failures_by_source: dict[str, int] = {}
        for audit_id, observed, action, ip_address in rows:
            observed = float(observed or now)
            last_event_at = max(last_event_at, observed)
            action_clean = " ".join(str(action or "").split()).casefold()[:80]
            failure = ("login" in action_clean or "sign" in action_clean) and any(
                token in action_clean for token in ("fail", "error", "invalid", "denied")
            )
            success = ("login" in action_clean or "sign" in action_clean) and any(
                token in action_clean for token in ("success", "login", "signin", "sign_in")
            ) and not failure
            kind = "supabase_auth_failure" if failure else "supabase_auth_success" if success else "supabase_auth_audit"
            source_key = pseudonym(secret, "supabase-source", str(ip_address)) if ip_address else ""
            subject_key = pseudonym(secret, "supabase-audit", str(audit_id))
            identity = str(uuid5(NAMESPACE_URL, "doobielogic:supabase-auth:" + str(audit_id)))
            events.append(dict(id=identity, occurred_at=observed, kind=kind, subject_key=subject_key,
                               source_key=source_key, actor_id="", organization_id="",
                               route=("supabase_auth:" + action_clean)[:200],
                               request_id="", audit_id=identity))
            if failure:
                failures_by_source[source_key or "unknown"] = failures_by_source.get(source_key or "unknown", 0) + 1
        with Session(engine) as session, session.begin():
            append_events(session, events)
            for key, count in failures_by_source.items():
                if count >= 5:
                    open_incident(session, "supabase_auth_failures", key, count, now,
                                  {"source": "supabase_auth", "new_failures": count,
                                   "payload_collected": False}, "high")
            return _upsert_state(session, source_id=source_id, now=now,
                                 status="connected_empty" if not rows else status,
                                 failures=prior_failures, last_event_at=last_event_at,
                                 detail={"security_events": True, "new_events": len(events),
                                         "payload_collected": False})
    except Exception as exc:
        category = _category(exc)
        with Session(engine) as session, session.begin():
            return _upsert_state(session, source_id=source_id, now=now,
                                 status="permission_unavailable" if category == "permission_denied" else "degraded",
                                 failures=prior_failures + 1, last_error_category=category,
                                 last_event_at=float(prior.last_event_at or 0) if prior else 0,
                                 detail={"security_events": False, "error_category": category})


def collect_cloudflare_liveness(engine, now: float):
    source_id = "cloudflare:tunnel"
    with Session(engine) as session:
        prior = _state(session, source_id)
        prior_failures = int(prior.failures or 0) if prior else 0
    if os.name != "nt":
        status, running = "not_available", False
    else:
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "@(Get-Process cloudflared -ErrorAction SilentlyContinue).Count"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            running = int(result.stdout.strip() or 0) > 0
            status = "tunnel_liveness_only" if running else "tunnel_not_running"
        except Exception:
            running, status = False, "liveness_unavailable"
    with Session(engine) as session, session.begin():
        return _upsert_state(session, source_id=source_id, now=now, status=status,
                             failures=prior_failures + (0 if running or status == "not_available" else 1),
                             last_error_category="" if running else ("tunnel_not_running" if status == "tunnel_not_running" else ""),
                             detail={"tunnel_running": running, "security_event_feed": False})


class PerimeterCollector:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.last_run = 0.0

    def tick(self, now=None):
        now = time.time() if now is None else float(now)
        if now - self.last_run < SOURCE_INTERVAL:
            return
        self.last_run = now
        # Perimeter sources are best-effort. Even a source-state write failure must
        # never convert healthy core monitoring into a false outage.
        for collector, args in (
            (collect_defender, (self.engine, self.settings.security_hmac_secret, now)),
            (collect_supabase_auth, (self.engine, self.settings.security_hmac_secret, now)),
            (collect_cloudflare_liveness, (self.engine, now)),
        ):
            try:
                collector(*args)
            except Exception:
                continue

    def public(self):
        try:
            with Session(self.engine) as session:
                rows = list(session.scalars(select(SecuritySourceState).order_by(SecuritySourceState.id)))
            return {row.id: {
                "checked_at": row.checked_at, "status": row.status, "failures": row.failures,
                "last_error_category": row.last_error_category, "last_event_at": row.last_event_at,
                "detail": json.loads(row.detail_json or "{}"),
            } for row in rows}
        except SQLAlchemyError:
            return {}
