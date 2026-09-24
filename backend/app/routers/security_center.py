"""Platform-DEV-only incident review; no public telemetry ingestion."""
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select, func, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from ..auth import RequestContext, get_request_context, bearer
from ..database import get_engine
from ..security.models import SecurityIncident, SecurityMonitorState
from ..security.store import serialize_incident
from modules.coman.audit import record_audit_event

router = APIRouter(prefix="/security", tags=["security-center"])


def security_context(context: RequestContext = Depends(get_request_context),
                     credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, "An authenticated platform session is required.")
    if context.role != "dev":
        raise HTTPException(403, "Platform DEV access is required.")
    return context


@router.get("/status")
def status(request: Request, context=Depends(security_context), engine: Engine = Depends(get_engine)):
    monitor = getattr(request.app.state, "security_monitor", None)
    health = monitor.health() if monitor else {"state": "not_started", "notifications": "not_connected"}
    try:
        with Session(engine) as session:
            workers = session.execute(select(SecurityMonitorState.checked_at, SecurityMonitorState.status,
                SecurityMonitorState.dropped, SecurityMonitorState.failures)
                .where(SecurityMonitorState.id.like("worker:%"), SecurityMonitorState.checked_at >= time.time() - 86400)
                .order_by(SecurityMonitorState.checked_at.desc()).limit(20)).all()
            active = session.scalar(select(func.count()).select_from(SecurityIncident).where(SecurityIncident.status != "resolved"))
        return {**health, "open_incidents": active, "workers": [dict(checked_at=t, state=s, dropped=d, failures=f,
            stale=time.time() - t > 30) for t,s,d,f in workers]}
    except SQLAlchemyError:
        raise HTTPException(503, "Security storage unavailable; monitoring coverage is not verified.") from None


@router.get("/incidents")
def incidents(context=Depends(security_context), engine: Engine = Depends(get_engine),
              offset: int = Query(0, ge=0, le=10000), limit: int = Query(25, ge=1, le=100)):
    try:
        with Session(engine) as session:
            total = session.scalar(select(func.count()).select_from(SecurityIncident)) or 0
            rows = session.scalars(select(SecurityIncident).order_by(SecurityIncident.last_seen.desc(),
                SecurityIncident.id).offset(offset).limit(limit)).all()
            return {"items": [serialize_incident(row) for row in rows], "total": total,
                    "offset": offset, "limit": limit, "has_more": offset + limit < total}
    except SQLAlchemyError:
        raise HTTPException(503, "Security incident history is unavailable.") from None


class Triage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "acknowledged", "resolved"]
    expected_version: int = Field(ge=1)


@router.post("/incidents/{incident_id}/triage")
def triage(incident_id: str, payload: Triage, context: RequestContext = Depends(security_context),
           engine: Engine = Depends(get_engine)):
    try:
        with Session(engine) as session, session.begin():
            row = session.get(SecurityIncident, incident_id)
            if row is None:
                raise HTTPException(404, "Incident not found.")
            before = row.status
            count = session.execute(update(SecurityIncident).where(SecurityIncident.id == incident_id,
                SecurityIncident.version == payload.expected_version).values(status=payload.status,
                    version=SecurityIncident.version + 1)).rowcount
            if count != 1:
                raise HTTPException(409, "This incident changed; refresh before updating it.")
            record_audit_event(session, organization_id=context.organization_id, facility_id=context.facility_id,
                entity_type="security_incident", entity_id=incident_id, action="security_incident_triaged",
                actor=context.user_id, before={"status": before}, after={"status": payload.status}, source="user")
            session.flush(); session.refresh(row)
            return serialize_incident(row)
    except SQLAlchemyError:
        raise HTTPException(503, "Incident update could not be saved.") from None
