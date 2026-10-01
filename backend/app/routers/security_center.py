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
from ..config import Settings, get_settings
from ..security.privacy import pseudonym
from modules.coman.models import AppUser
from ..security.models import SecurityIncident, SecurityMonitorState, SecurityGuardState, SecurityInvestigation
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
            workers = session.execute(select(
                SecurityMonitorState.checked_at, SecurityMonitorState.status,
                SecurityMonitorState.dropped, SecurityMonitorState.failures,
                SecurityMonitorState.last_error_category, SecurityMonitorState.last_error_at,
                SecurityMonitorState.clean_cycles,
            ).where(
                SecurityMonitorState.id.like("worker:%"),
                SecurityMonitorState.checked_at >= time.time() - 86400,
            ).order_by(SecurityMonitorState.checked_at.desc()).limit(20)).all()
            active = session.scalar(select(func.count()).select_from(SecurityIncident).where(
                SecurityIncident.status.in_(("open", "acknowledged"))
            ))
        return {**health, "open_incidents": active, "workers": [
            dict(checked_at=t, state=s, dropped=d, failures=f,
                 last_error_category=category or None, last_error_at=error_at or None,
                 clean_cycles=clean, stale=time.time() - t > 30)
            for t,s,d,f,category,error_at,clean in workers
        ]}
    except SQLAlchemyError:
        raise HTTPException(503, "Security storage unavailable; monitoring coverage is not verified.") from None


@router.get("/guard")
def guard_status(context=Depends(security_context), engine: Engine = Depends(get_engine)):
    try:
        with Session(engine) as session:
            guard = session.get(SecurityGuardState, "guard:primary")
            investigations = list(session.scalars(
                select(SecurityInvestigation).where(SecurityInvestigation.status == "open")
                .order_by(SecurityInvestigation.risk_score.desc(), SecurityInvestigation.updated_at.desc()).limit(25)
            ))
        if guard is None:
            return {"state":"starting","threat_level":"unknown","metrc_write_protection":True,"deception_armed":True,"investigations":[]}
        return {
            "state":guard.state,"checked_at":guard.checked_at,"threat_level":guard.threat_level,
            "risk_score":guard.risk_score,"active_investigations":guard.active_investigations,
            "metrc_write_protection":guard.metrc_write_protection,"deception_armed":guard.deception_armed,
            "ai_state":guard.ai_state,"ai_last_success":guard.ai_last_success,
            "investigations":[{
                "id":x.id,"updated_at":x.updated_at,"risk_score":x.risk_score,"confidence":x.confidence,
                "classification":x.classification,"recommended_state":x.recommended_state,
                "evidence_hash":x.evidence_hash,"ai_summary":x.ai_summary,
            } for x in investigations],
        }
    except SQLAlchemyError:
        raise HTTPException(503, "Security Guard state is unavailable; regulatory writes should remain protected.") from None


class ResolveKnownAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_key: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


@router.post("/resolve-known-account")
def resolve_known_account(payload: ResolveKnownAccount, context=Depends(security_context),
                          engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    """Compare one existing Security Center fingerprint to known accounts without exposing the HMAC key."""
    if len(settings.security_hmac_secret) < 32:
        raise HTTPException(503, "Security pseudonymization is not configured.")
    try:
        with Session(engine) as session:
            rows = session.execute(select(AppUser.id, AppUser.username, AppUser.active)).all()
        matches = []
        for user_id, username, active in rows:
            normalized = str(username or "").strip().casefold()
            if normalized and pseudonym(settings.security_hmac_secret, "subject", normalized) == payload.subject_key:
                matches.append({"user_id":str(user_id),"username":str(username),"active":bool(active)})
        if len(matches) > 1:
            raise HTTPException(409, "Security fingerprint matched more than one account; manual review required.")
        result = matches[0] if matches else None
        with Session(engine) as session, session.begin():
            record_audit_event(session, organization_id=context.organization_id, facility_id=context.facility_id,
                               entity_type="security_incident", entity_id=payload.subject_key[:12],
                               action="known_account_fingerprint_resolved", actor=context.user_id,
                               changes={"matched":bool(result)})
        return {"known_account":bool(result),"account":result}
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(503, "Known-account fingerprint resolution is unavailable.") from None


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
