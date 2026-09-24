"""Bounded deterministic detection; database uniqueness prevents duplicate alerts."""
import hashlib
import json
from uuid import uuid4, uuid5, NAMESPACE_URL
from datetime import datetime, timezone
from sqlalchemy import select, func, delete
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
    fingerprint = hashlib.sha256(f"{rule}:{key}:{int(now // COOLDOWN)}".encode()).hexdigest()
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
    E = SecurityEvent
    recent = (E.occurred_at >= now - WINDOW, E.occurred_at <= now)
    findings = []
    failed = session.execute(select(E.subject_key, func.count(), func.max(E.occurred_at)).where(
        *recent, E.kind == "login_failure", E.subject_key != "").group_by(E.subject_key)
        .having(func.count() >= 8).order_by(func.count().desc()).limit(100)).all()
    keys = [key for key, _, _ in failed]
    successes = dict(session.execute(select(E.subject_key, func.max(E.occurred_at)).where(
        *recent, E.kind == "login_success", E.subject_key.in_(keys)).group_by(E.subject_key)).all())
    for key, count, last_failure in failed:
        findings.append(("login_failures", key, count, "username_sign_in_denied"))
        if successes.get(key, 0) > last_failure:
            findings.append(("login_after_failures", key, count, "review_session_not_confirmed_compromise"))
