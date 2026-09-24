"""Keep derived security telemetry bounded without changing business ledgers."""
from sqlalchemy import select, delete, func
from .models import SecurityEvent, SecurityIncident, SecurityMonitorState


def maintain(session, now):
    # Retention applies only to derived observations and resolved incidents.
    for model, column, horizon, extra in (
        (SecurityEvent, SecurityEvent.occurred_at, 7 * 86400, ()),
        (SecurityIncident, SecurityIncident.last_seen, 90 * 86400, (SecurityIncident.status == "resolved",)),
        (SecurityMonitorState, SecurityMonitorState.checked_at, 7 * 86400, (SecurityMonitorState.id.like("worker:%"),)),
    ):
        selected = select(model.id).where(column < now - horizon, *extra).order_by(column).limit(1000)
        session.execute(delete(model).where(model.id.in_(selected)))


def available_capacity(session, maximum):
    total = session.scalar(select(func.count()).select_from(SecurityEvent)) or 0
    return max(0, maximum - total)
