"""Bounded deterministic detection; database uniqueness prevents duplicate alerts."""
import hashlib
import json
from uuid import uuid4, uuid5, NAMESPACE_URL
from datetime import datetime, timezone
from sqlalchemy import select
from modules.coman.models import AuditEvent
from .models import SecurityEvent, SecurityIncident, SecurityMonitorState
from .privacy import pseudonym

WINDOW = 300
COOLDOWN = 900
PRIVILEGED_ACTIONS = ("authorization_updated", "password_reset_by_admin", "supabase_account_linked")
TITLES = {
    "login_failures": "Repeated failed username sign-ins",
    "password_spray": "Failed sign-ins across multiple accounts",
    "login_after_failures": "Successful sign-in after repeated failures",
    "scope_denials": "Repeated denied organization or facility access",
    "privileged_change": "Sensitive account administration recorded",
    "monitoring_degraded": "Security monitoring lost observations or encountered errors",
    "test_alert": "TEST: DoobieLogic security notification",
}


def insert_for(session, model):
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif session.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Security storage requires PostgreSQL or isolated SQLite")
    return insert(model)


def append_events(session, events):
    if events:
        session.execute(insert_for(session, SecurityEvent).values(events).on_conflict_do_nothing(index_elements=["id"]))


def open_incident(session, rule, key, count, now, evidence=None, severity="high"):
    # Rolling detection window; explicit fixed 15-minute alert deduplication bucket.
    bucket = 0 if rule == "privileged_change" else int(now // COOLDOWN)
    fingerprint = hashlib.sha256(f"{rule}:{key}:{bucket}".encode()).hexdigest()
    values = dict(id=str(uuid4()), fingerprint=fingerprint, rule=rule, severity=severity,
                  title=TITLES[rule], group_key=key, first_seen=now, last_seen=now,
                  occurrences=count, status="open", version=1, evidence_json=json.dumps(evidence or {}),
                  notification_status="pending", notification_updated_at=0,
                  notification_reference="", notification_attempts=0)
    session.execute(insert_for(session, SecurityIncident).values(**values).on_conflict_do_update(
        index_elements=["fingerprint"], set_={"last_seen": now, "occurrences": count,
        "evidence_json": values["evidence_json"]}))
    return session.scalar(select(SecurityIncident).where(SecurityIncident.fingerprint == fingerprint))


def collect_privileged_audits(session, secret, now):
    cutoff = datetime.fromtimestamp(now - WINDOW, timezone.utc)
    rows = session.execute(select(AuditEvent.id, AuditEvent.occurred_at, AuditEvent.actor,
                AuditEvent.organization_id, AuditEvent.action).where(
        AuditEvent.entity_type == "app_user", AuditEvent.action.in_(PRIVILEGED_ACTIONS),
        AuditEvent.occurred_at >= cutoff).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id).limit(201)).all()
    events = []
    for row in rows[:200]:
        timestamp = row.occurred_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        events.append(dict(id=str(uuid5(NAMESPACE_URL, "doobielogic-security-audit:" + row.id)),
            occurred_at=timestamp.timestamp(), kind="privileged_change",
            subject_key=pseudonym(secret, "audit", row.id), source_key="",
            actor_id=row.actor[:36], organization_id=row.organization_id,
            route="canonical:app_user:" + row.action, request_id="", audit_id=row.id))
    append_events(session, events)
    return len(rows) > 200


def detect(session, now):
    from .rules import evaluate
    findings, saturated = evaluate(session, now)
    for rule, key, count, evidence in findings:
        evidence["window_seconds"] = WINDOW
        open_incident(session, rule, key, count, now, evidence)
    return saturated


def serialize_incident(row):
    fields = ("id", "rule", "severity", "title", "first_seen", "last_seen", "occurrences",
              "status", "version", "notification_status", "notification_reference", "notification_attempts")
    return {**{field: getattr(row, field) for field in fields}, "evidence": json.loads(row.evidence_json)}
