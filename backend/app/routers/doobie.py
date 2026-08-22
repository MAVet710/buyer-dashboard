import json
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from modules.doobie_actions.service import ALLOWED_ACTIONS, DoobieActionService
from ..auth import RequestContext, get_request_context
from ..database import get_engine
router = APIRouter(prefix="/doobie", tags=["doobie"])
APPROVAL_ROLES = {"dev", "admin", "supervisor"}

class ProposalCreate(BaseModel):
    action_type: str
    title: str
    rationale: str = ""
    payload: dict = Field(default_factory=dict)
    preview: dict = Field(default_factory=dict)
    financial_impact_usd: float = 0
    risk_level: str = "medium"
    idempotency_key: str = ""

def _item(row):
    return {key: getattr(row, key) for key in ("id", "action_type", "title", "rationale", "financial_impact_usd", "risk_level", "status", "source_type", "source_id", "created_by", "approved_by", "approved_at", "expires_at", "created_at")} | {"payload": json.loads(row.payload_json or "{}"), "preview": json.loads(row.preview_json or "{}")}

@router.get("/actions")
def actions(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return {"allowed_actions": sorted(ALLOWED_ACTIONS), "items": [_item(row) for row in DoobieActionService(engine).list_proposals(context.organization_id, context.facility_id, statuses=("proposed", "approved", "executing", "executed", "rejected", "failed", "expired"))]}

@router.post("/actions", status_code=201)
def propose(payload: ProposalCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _item(DoobieActionService(engine).propose(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, idempotency_key=payload.idempotency_key or f"web:{uuid4()}", source_type="web", **payload.model_dump(exclude={"idempotency_key"})))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/actions/{proposal_id}/{action}")
def decide(proposal_id: str, action: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in APPROVAL_ROLES: raise HTTPException(403, "Your role cannot approve or execute Doobie actions.")
    service = DoobieActionService(engine)
    try:
        if action == "approve": return _item(service.approve(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id))
        if action == "reject": return _item(service.reject(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id))
        if action == "execute": return service.execute(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id)
        raise HTTPException(404, "Unsupported Doobie action decision.")
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
