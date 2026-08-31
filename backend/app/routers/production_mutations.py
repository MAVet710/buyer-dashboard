from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.material_lineage.service import MaterialLineageService
from modules.production_erp.mutations import MUTATION_ACTIONS, ProductionMutationService
from modules.production_erp.run360_mutations import ProductionRun360MutationService
from ..auth import (
    RequestContext,
    get_request_context,
    get_production_context,
    require_any_facility_capability,
    require_facility_capability,
)
from ..database import get_engine

router = APIRouter()
production_router = APIRouter(
    prefix="/production",
    tags=["production"],
    dependencies=[Depends(get_production_context)],
)
cultivation_router = APIRouter(prefix="/inventory/production/plants", tags=["cultivation"])
lineage_router = APIRouter(prefix="/material-lineage", tags=["traceability"])


class MutationPreviewRequest(BaseModel):
    action_type: str
    payload: dict = Field(default_factory=dict)


class MutationCommitRequest(MutationPreviewRequest):
    preview_key: str


class HarvestOutputItem(BaseModel):
    product_id: str
    lot_code: str
    quantity: float
    unit: str = "g"
    purpose: str = "other"
    measurement_basis: str = "dry"
    location_code: str = "HARVEST-OUTPUT"
    status: str = "quarantine"
    compliance_package_id: str = ""


class HarvestLossItem(BaseModel):
    quantity: float
    unit: str = "g"
    loss_type: str = "process_loss"
    measurement_basis: str = "dry"
    reason: str = ""


class HarvestAllocationRequest(BaseModel):
    outputs: list[HarvestOutputItem]
    losses: list[HarvestLossItem] = Field(default_factory=list)


def _service(engine: Engine) -> ProductionMutationService:
    return ProductionRun360MutationService(engine)


def _guard_qa(action_type: str, context: RequestContext) -> None:
    if action_type == "qa_decision" and context.role.casefold() not in {"dev", "admin", "supervisor", "qa"}:
        raise HTTPException(403, "Your role cannot post QA decisions.")


def _guard_cultivation_write(context: RequestContext, engine: Engine) -> None:
    require_facility_capability(context, engine, "cultivation")
    if context.role.casefold() not in {"dev", "admin", "supervisor", "operator", "qa"}:
        raise HTTPException(403, "Your role does not allow cultivation inventory changes.")


@production_router.get("/mutation-actions")
def mutation_actions() -> dict[str, list[str]]:
    return {"allowed_actions": sorted(MUTATION_ACTIONS)}


@production_router.post("/orders/{order_id}/mutations/preview")
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


@production_router.post("/orders/{order_id}/mutations/commit")
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


@cultivation_router.post("/harvests/{harvest_id}/outputs/preview")
def preview_harvest_outputs(
    harvest_id: str,
    payload: HarvestAllocationRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_cultivation_write(context, engine)
    try:
        return MaterialLineageService(engine).preview_harvest_allocation(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            harvest_id=harvest_id,
            outputs=[row.model_dump() for row in payload.outputs],
            losses=[row.model_dump() for row in payload.losses],
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@cultivation_router.post("/harvests/{harvest_id}/outputs/commit", status_code=201)
def commit_harvest_outputs(
    harvest_id: str,
    payload: HarvestAllocationRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_cultivation_write(context, engine)
    try:
        return MaterialLineageService(engine).commit_harvest_allocation(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            harvest_id=harvest_id,
            outputs=[row.model_dump() for row in payload.outputs],
            losses=[row.model_dump() for row in payload.losses],
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@lineage_router.get("/lots/{lot_id}")
def lot_lineage_graph(
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_any_facility_capability(context, engine, ("retail", "production", "cultivation"))
    try:
        return MaterialLineageService(engine).lot_graph(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            lot_id=lot_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


router.include_router(production_router)
router.include_router(cultivation_router)
router.include_router(lineage_router)
