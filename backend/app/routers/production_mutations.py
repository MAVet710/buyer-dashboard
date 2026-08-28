from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.production_erp.mutations import MUTATION_ACTIONS, ProductionMutationService
from modules.production_erp.run360_mutations import ProductionRun360MutationService
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine

router = APIRouter(
    prefix="/production",
    tags=["production"],
    dependencies=[Depends(get_production_context)],
)


class MutationPreviewRequest(BaseModel):
    action_type: str
    payload: dict = Field(default_factory=dict)


class MutationCommitRequest(MutationPreviewRequest):
    preview_key: str


def _service(engine: Engine) -> ProductionMutationService:
    return ProductionRun360MutationService(engine)


def _guard_qa(action_type: str, context: RequestContext) -> None:
    if action_type == "qa_decision" and context.role.casefold() not in {"dev", "admin", "supervisor", "qa"}:
        raise HTTPException(403, "Your role cannot post QA decisions.")


@router.get("/mutation-actions")
def mutation_actions() -> dict[str, list[str]]:
    return {"allowed_actions": sorted(MUTATION_ACTIONS)}


@router.post("/orders/{order_id}/mutations/preview")
def preview_mutation(
    order_id: str,
    payload: MutationPreviewRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_qa(payload.action_type, context)
    try:
        return _service(engine).preview(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            order_id=order_id,
            action_type=payload.action_type,
            payload=payload.payload,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/orders/{order_id}/mutations/commit")
def commit_mutation(
    order_id: str,
    payload: MutationCommitRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_qa(payload.action_type, context)
    try:
        return _service(engine).commit(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            order_id=order_id,
            action_type=payload.action_type,
            payload=payload.payload,
            preview_key=payload.preview_key,
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
