"""Read-only rule evaluation. Findings are suspicions, never proof of compromise."""
from sqlalchemy import select, func
from .models import SecurityEvent as E

WINDOW_SECONDS = 300
MAX_GROUPS = 100


def evaluate(session, now):
    recent = (E.occurred_at >= now - WINDOW_SECONDS, E.occurred_at <= now)
    findings = []
    failures = session.execute(select(E.subject_key, func.count(), func.max(E.occurred_at)).where(
        *recent, E.kind == "login_failure", E.subject_key != "").group_by(E.subject_key)
        .having(func.count() >= 8).order_by(func.count().desc(), E.subject_key).limit(MAX_GROUPS + 1)).all()
    subjects = [key for key, _, _ in failures[:MAX_GROUPS]]
    success_times = select(E.subject_key.label("subject"), func.max(E.occurred_at).label("success_at")).where(
        *recent, E.kind == "login_success", E.subject_key.in_(subjects)).group_by(E.subject_key).subquery()
    suspicious_successes = set(session.scalars(select(E.subject_key).join(success_times,
        success_times.c.subject == E.subject_key).where(*recent, E.kind == "login_failure",
        E.occurred_at < success_times.c.success_at).group_by(E.subject_key).having(func.count() >= 8)))
    saturated = len(failures) > MAX_GROUPS
    for key, count, _ in failures[:MAX_GROUPS]:
        findings.append(("login_failures", key, count, {"outcome": "sign_ins_denied"}))
        if key in suspicious_successes:
            findings.append(("login_after_failures", key, count, {"outcome": "review_session_not_confirmed_compromise"}))
    sources = session.execute(select(E.source_key, func.count()).where(
        *recent, E.kind == "login_failure", E.source_key != "", E.subject_key != "")
        .group_by(E.source_key).having(func.count() >= 20, func.count(func.distinct(E.subject_key)) >= 5)
        .order_by(func.count().desc(), E.source_key).limit(MAX_GROUPS + 1)).all()
    saturated |= len(sources) > MAX_GROUPS
    for key, count in sources[:MAX_GROUPS]:
        findings.append(("password_spray", key, count, {"outcome": "sign_ins_denied"}))
    denied = session.execute(select(E.subject_key, func.count()).where(
        *recent, E.kind == "scope_denial", E.subject_key != "").group_by(E.subject_key)
        .having(func.count() >= 10).order_by(func.count().desc(), E.subject_key).limit(MAX_GROUPS + 1)).all()
    saturated |= len(denied) > MAX_GROUPS
    for key, count in denied[:MAX_GROUPS]:
        findings.append(("scope_denials", key, count, {"outcome": "all_observed_requests_denied"}))
    privileged = session.execute(select(E.subject_key, E.audit_id, E.actor_id).where(
        *recent, E.kind == "privileged_change").order_by(E.occurred_at.desc(), E.id).limit(MAX_GROUPS + 1)).all()
    saturated |= len(privileged) > MAX_GROUPS
    for key, audit_id, actor_id in privileged[:MAX_GROUPS]:
        findings.append(("privileged_change", key, 1, {"audit_id": audit_id, "actor_id": actor_id,
                                                     "outcome": "review_recorded_change"}))
    return findings, saturated
