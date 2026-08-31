from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.recall.service import Recall360Service
from ..auth import RequestContext, get_request_context, require_any_facility_capability
from ..database import get_engine
from ..services.facility_access import accessible_facility_ids

router = APIRouter(prefix="/recall", tags=["recall"])
CONTAINMENT_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


class RecallHoldRequest(BaseModel):
    root_type: str = Field(pattern="^(package|lot|plant|harvest)$")
    reference: str = Field(min_length=1, max_length=255)
    reason: str = Field(default="Recall containment", min_length=3, max_length=255)


class RecallHoldCommit(RecallHoldRequest):
    preview_key: str = Field(min_length=64, max_length=64)


def _scope(context: RequestContext, engine: Engine) -> set[str]:
    require_any_facility_capability(context, engine, ("retail", "production", "cultivation"))
    return accessible_facility_ids(context, engine)


def _require_containment_role(context: RequestContext) -> None:
    if context.role.casefold() not in CONTAINMENT_ROLES:
        raise HTTPException(403, "Your role may review Recall 360 but cannot place inventory on operational hold.")


@router.get("/impact")
def recall_impact(
    root_type: str = Query(pattern="^(package|lot|plant|harvest)$"),
    reference: str = Query(min_length=1, max_length=255),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    allowed = _scope(context, engine)
    try:
        return Recall360Service(engine).impact(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            root_type=root_type,
            reference=reference,
            allowed_facility_ids=allowed,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/containment/preview")
def preview_recall_containment(
    payload: RecallHoldRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_containment_role(context)
    allowed = _scope(context, engine)
    try:
        return Recall360Service(engine).preview_local_hold(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            root_type=payload.root_type,
            reference=payload.reference,
            allowed_facility_ids=allowed,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/containment/commit")
def commit_recall_containment(
    payload: RecallHoldCommit,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_containment_role(context)
    allowed = _scope(context, engine)
    try:
        return Recall360Service(engine).commit_local_hold(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            root_type=payload.root_type,
            reference=payload.reference,
            allowed_facility_ids=allowed,
            reason=payload.reason,
            preview_key=payload.preview_key,
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
