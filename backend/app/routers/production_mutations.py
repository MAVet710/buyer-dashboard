from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.cultivation.post_harvest import POST_HARVEST_STAGES, PostHarvestService
from modules.inventory_transfers.lineage import CrossFacilityLineageService
from modules.inventory_transfers.recall import RecallBlastRadiusService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.production_erp.calendar_read_model import production_calendar_workspace
from modules.production_erp.integrity_mutations import ProductionIntegrityMutationService
from modules.production_erp.mutations import MUTATION_ACTIONS, ProductionMutationService
from ..auth import (
    RequestContext,
    get_request_context,
    get_production_context,
    require_any_facility_capability,
    require_facility_capability,
)
from ..database import get_engine
from ..services.facility_access import accessible_facility_ids

router = APIRouter()
production_router = APIRouter(
    prefix="/production",
    tags=["production"],
    dependencies=[Depends(get_production_context)],
)
cultivation_router = APIRouter(prefix="/inventory/production/plants", tags=["cultivation"])
lineage_router = APIRouter(prefix="/material-lineage", tags=["traceability"])

_POST_HARVEST_STAGE_ORDER = {stage: index for index, stage in enumerate(POST_HARVEST_STAGES)}
_POST_HARVEST_OUTPUT_TYPES = ("finished_flower", "trim", "biomass", "waste")
_POST_HARVEST_WEIGHT_TYPES = ("wip", *_POST_HARVEST_OUTPUT_TYPES)
_POST_HARVEST_TOLERANCE_G = 1.0


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


class HarvestAllocationCommitRequest(HarvestAllocationRequest):
    preview_key: str


class PostHarvestStageRequest(BaseModel):
    stage: str = Field(min_length=1, max_length=24)
    location_code: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=4000)


class PostHarvestMeasurement(BaseModel):
    weight_type: str = Field(min_length=1, max_length=32)
    quantity_g: float = Field(ge=0)
    container_code: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=1000)


class PostHarvestWeightsRequest(BaseModel):
    measurements: list[PostHarvestMeasurement] = Field(min_length=1, max_length=5)
    correction_reason: str = Field(default="", max_length=1000)


def _service(engine: Engine) -> ProductionMutationService:
    return ProductionIntegrityMutationService(engine)


def _guard_mutation(action_type: str, context: RequestContext) -> None:
    role = context.role.casefold()
    if action_type == "qa_decision" and role not in {"dev", "admin", "supervisor", "qa"}:
        raise HTTPException(403, "Your role cannot post QA decisions.")
    if action_type == "consume_materials" and role not in {"dev", "admin", "supervisor", "operator", "qa"}:
        raise HTTPException(403, "Your role cannot post physical production consumption.")


def _guard_cultivation_write(context: RequestContext, engine: Engine) -> None:
    require_facility_capability(context, engine, "cultivation")
    if context.role.casefold() not in {"dev", "admin", "supervisor", "operator", "qa"}:
        raise HTTPException(403, "Your role does not allow cultivation inventory changes.")


def _can_correct_locked_post_harvest(context: RequestContext) -> bool:
    return context.role.casefold() in {"dev", "admin", "supervisor", "qa"}


def _validate_post_harvest_stage_step(current_stage: str, target_stage: str) -> str:
    current = current_stage.strip().casefold()
    target = target_stage.strip().casefold()
    if current not in _POST_HARVEST_STAGE_ORDER or target not in _POST_HARVEST_STAGE_ORDER:
        raise HTTPException(422, "Unsupported post-harvest stage.")
    if target == current:
        return target
    expected_index = _POST_HARVEST_STAGE_ORDER[current] + 1
    if expected_index >= len(POST_HARVEST_STAGES) or _POST_HARVEST_STAGE_ORDER[target] != expected_index:
        expected = POST_HARVEST_STAGES[expected_index] if expected_index < len(POST_HARVEST_STAGES) else "no later stage"
        raise HTTPException(
            422,
            f"Post-harvest work must advance one stage at a time. {current} can move next to {expected}, not {target}.",
        )
    return target


def _normalized_post_harvest_measurements(measurements: list[PostHarvestMeasurement]) -> list[dict]:
    rows = [row.model_dump() for row in measurements]
    seen: set[str] = set()
    for row in rows:
        kind = str(row.get("weight_type") or "").strip().casefold()
        if kind not in _POST_HARVEST_WEIGHT_TYPES:
            raise HTTPException(422, "Unsupported post-harvest weight type.")
        if kind in seen:
            raise HTTPException(422, f"Submit only one {kind} reading per weight update.")
        seen.add(kind)
        row["weight_type"] = kind
    return rows


def _guard_reconciled_post_harvest(current: dict, measurements: list[dict] | None = None) -> None:
    dry_weight = float(current.get("dry_weight_g") or 0)
    if dry_weight <= 0:
        raise HTTPException(422, "Record the canonical dry harvest weight before approving final post-harvest reconciliation.")

    weights = {key: float(value or 0) for key, value in dict(current.get("current_weights") or {}).items()}
    for row in measurements or []:
        weights[str(row.get("weight_type") or "").strip().casefold()] = float(row.get("quantity_g") or 0)

    accounted = sum(weights.get(kind, 0.0) for kind in _POST_HARVEST_OUTPUT_TYPES)
    discrepancy = round(dry_weight - accounted, 4)
    if abs(discrepancy) > _POST_HARVEST_TOLERANCE_G:
        direction = "remaining" if discrepancy > 0 else "over-recorded"
        raise HTTPException(
            422,
            f"Final post-harvest weights are not reconciled: {abs(discrepancy):,.2f} g {direction}. Record flower, trim, biomass, or waste until the dry weight reconciles within 1 g.",
        )

    wip = float(weights.get("wip") or 0)
    if wip > _POST_HARVEST_TOLERANCE_G:
        raise HTTPException(
            422,
            f"Final post-harvest reconciliation still reports {wip:,.2f} g of remaining/WIP material. Record the final WIP reading at 0 g before approval.",
        )


def _guard_post_harvest_ready(service: PostHarvestService, context: RequestContext, batch_id: str) -> None:
    if not _can_correct_locked_post_harvest(context):
        raise HTTPException(403, "A supervisor, QA user, or administrator must approve final post-harvest reconciliation.")
    try:
        current = service.detail(context.organization_id, context.facility_id, batch_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    _guard_reconciled_post_harvest(current)


@production_router.get("/calendar-workspace")
def calendar_workspace(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    return production_calendar_workspace(engine, context.organization_id, context.facility_id)


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
    _guard_mutation(payload.action_type, context)
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
    _guard_mutation(payload.action_type, context)
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


@cultivation_router.get("/post-harvest")
def list_post_harvest(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_facility_capability(context, engine, "cultivation")
    return {"items": PostHarvestService(engine).list_batches(context.organization_id, context.facility_id)}


@cultivation_router.post("/post-harvest/sync")
def sync_post_harvest(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_cultivation_write(context, engine)
    try:
        return {
            "items": PostHarvestService(engine).sync_open_harvests(
                context.organization_id,
                context.facility_id,
                actor=context.user_id,
            )
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@cultivation_router.get("/post-harvest/{batch_id}")
def post_harvest_detail(
    batch_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_facility_capability(context, engine, "cultivation")
    try:
        return PostHarvestService(engine).detail(context.organization_id, context.facility_id, batch_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@cultivation_router.post("/post-harvest/{batch_id}/transition")
def transition_post_harvest(
    batch_id: str,
    payload: PostHarvestStageRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_cultivation_write(context, engine)
    service = PostHarvestService(engine)
    try:
        current = service.detail(context.organization_id, context.facility_id, batch_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    target = _validate_post_harvest_stage_step(str(current.get("stage") or ""), payload.stage)
    if target == "ready":
        _guard_post_harvest_ready(service, context, batch_id)
    try:
        return service.transition(
            context.organization_id,
            context.facility_id,
            batch_id,
            stage=target,
            location_code=payload.location_code,
            notes=payload.notes,
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@cultivation_router.post("/post-harvest/{batch_id}/weights")
def record_post_harvest_weights(
    batch_id: str,
    payload: PostHarvestWeightsRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_cultivation_write(context, engine)
    service = PostHarvestService(engine)
    measurements = _normalized_post_harvest_measurements(payload.measurements)
    try:
        current = service.detail(context.organization_id, context.facility_id, batch_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if str(current.get("stage") or "").casefold() == "ready":
        if not _can_correct_locked_post_harvest(context):
            raise HTTPException(403, "A supervisor, QA user, or administrator must record locked post-harvest corrections.")
        if not payload.correction_reason.strip():
            raise HTTPException(422, "A correction reason is required when changing weights after the batch is ready.")
        _guard_reconciled_post_harvest(current, measurements)
    try:
        return service.record_weights(
            context.organization_id,
            context.facility_id,
            batch_id,
            measurements=measurements,
            actor=context.user_id,
            correction_reason=payload.correction_reason,
            allow_locked_correction=_can_correct_locked_post_harvest(context),
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
        return GuardedHarvestAllocationService(engine).preview_harvest_allocation(
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
    payload: HarvestAllocationCommitRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _guard_cultivation_write(context, engine)
    try:
        return GuardedHarvestAllocationService(engine).commit_harvest_allocation(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            harvest_id=harvest_id,
            outputs=[row.model_dump() for row in payload.outputs],
            losses=[row.model_dump() for row in payload.losses],
            preview_key=payload.preview_key,
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
        return CrossFacilityLineageService(engine).lot_graph(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            lot_id=lot_id,
            allowed_facility_ids=accessible_facility_ids(context, engine),
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@lineage_router.get("/lots/{lot_id}/recall")
def lot_recall_blast_radius(
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_any_facility_capability(context, engine, ("retail", "production", "cultivation"))
    try:
        return RecallBlastRadiusService(engine).blast_radius(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            lot_id=lot_id,
            allowed_facility_ids=accessible_facility_ids(context, engine),
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


router.include_router(production_router)
router.include_router(cultivation_router)
router.include_router(lineage_router)
