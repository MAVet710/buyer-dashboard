from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.regulatory.metrc_process_readiness import MetrcProcessReadinessService, MetrcTransferReadinessService
from services.metrc_production import fetch_all_available_package_tags, fetch_all_available_plant_tags

from ..auth import RequestContext, get_request_context, require_any_facility_capability, require_facility_capability, require_inventory_operation_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc

router = APIRouter(prefix="/metrc-readiness", tags=["metrc-readiness"])
WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow this Metrc-aligned operational change.")


def _cultivation(context: RequestContext, engine: Engine) -> None:
    require_facility_capability(context, engine, "cultivation")


def _inventory(context: RequestContext, engine: Engine) -> None:
    require_any_facility_capability(context, engine, ("retail", "production", "cultivation"))


def _records(result: dict[str, Any], message: str) -> list[dict[str, Any]]:
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or message))
    return [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]


class ImmatureGroupCreate(BaseModel):
    group_code: str = Field(min_length=1, max_length=120)
    group_type: Literal["clone_batch", "seed_batch", "nursery"] = "clone_batch"
    strain_name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=1, le=5000)
    origin_type: Literal["mother", "source_package", "transfer", "beginning_inventory", "state_authorized", "legacy_demo"]
    origin_reference: str = Field(default="", max_length=255)
    room_code: str = Field(default="UNASSIGNED", max_length=120)
    mother_plant_id: str | None = None
    source_lot_id: str | None = None
    planted_at: date | None = None
    estimated_harvest_date: date | None = None
    notes: str = Field(default="", max_length=4000)


class VegetativeTagAssignment(BaseModel):
    tag_labels: list[str] | None = Field(default=None, max_length=5000)
    provider_confirmed: bool = False
    provider_reference: str = Field(default="", max_length=255)


class TagReplacement(BaseModel):
    new_tag_label: str = Field(min_length=1, max_length=64)
    replace_date: date | None = None
    provider_confirmed: bool = False


class StrainCorrection(BaseModel):
    strain_name: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=255)
    provider_confirmed: bool = False


class HarvestPlantWeight(BaseModel):
    plant_id: str = Field(min_length=1, max_length=64)
    wet_weight_g: float = Field(ge=0)


class HarvestWeights(BaseModel):
    plant_weights: list[HarvestPlantWeight] = Field(min_length=1, max_length=5000)
    provider_confirmed: bool = False


class WasteCreate(BaseModel):
    target_type: Literal["plant", "plant_group", "harvest"]
    target_id: str = Field(min_length=1, max_length=64)
    method: str = Field(min_length=1, max_length=255)
    material_mixed: str = Field(default="", max_length=255)
    weight: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=24)
    reason: str = Field(min_length=1, max_length=255)
    waste_date: date = Field(default_factory=date.today)
    location: str = Field(min_length=1, max_length=160)
    notes: str = Field(default="", max_length=4000)
    provider_confirmed: bool = False


class ManicurePlantWeight(BaseModel):
    plant_id: str = Field(min_length=1, max_length=64)
    weight_g: float = Field(gt=0)


class ManicureCreate(BaseModel):
    batch_code: str = Field(min_length=1, max_length=120)
    source_phase: Literal["vegetative", "flowering"]
    location: str = Field(min_length=1, max_length=160)
    manicure_date: date = Field(default_factory=date.today)
    plant_weights: list[ManicurePlantWeight] = Field(min_length=1, max_length=5000)
    notes: str = Field(default="", max_length=4000)
    provider_confirmed: bool = False


class AdditiveCreate(BaseModel):
    target_type: Literal["plant", "plant_group", "location"]
    target_id: str = Field(min_length=1, max_length=160)
    product_name: str = Field(min_length=1, max_length=255)
    epa_number: str = Field(default="", max_length=120)
    supplier: str = Field(default="", max_length=255)
    amount: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)
    active_ingredients: str = Field(default="", max_length=4000)
    application_date: date = Field(default_factory=date.today)
    notes: str = Field(default="", max_length=4000)


class TestSampleCreate(BaseModel):
    source_type: Literal["harvest", "package"]
    source_id: str = Field(min_length=1, max_length=64)
    package_tag: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=32)
    provider_confirmed: bool = False
    provider_reference: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=4000)


class TestSampleConfirm(BaseModel):
    provider_reference: str = Field(min_length=1, max_length=255)


class TransferLine(BaseModel):
    source_lot_id: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0)


class WholePackageTransferCreate(BaseModel):
    destination_facility_id: str = Field(min_length=1, max_length=64)
    manifest_reference: str = Field(min_length=1, max_length=255)
    provider_transfer_id: str = Field(default="", max_length=255)
    state_transfer_confirmed: bool = False
    lines: list[TransferLine] = Field(min_length=1, max_length=500)
    notes: str = Field(default="", max_length=4000)


class TransferReceive(BaseModel):
    operation: Literal["retail", "production"]
    state_receipt_confirmed: bool = False
    lot_code: str = Field(default="", max_length=255)
    location: str = Field(default="RECEIVING", max_length=160)
    notes: str = Field(default="", max_length=4000)


class TransferDeparture(BaseModel):
    state_departure_confirmed: bool = False


class TransferReject(BaseModel):
    state_rejection_confirmed: bool = False
    reason: str = Field(min_length=1, max_length=255)
    notes: str = Field(default="", max_length=4000)
    return_manifest_reference: str = Field(default="", max_length=255)


class TransferReturn(BaseModel):
    state_return_confirmed: bool = False


@router.get("/status")
def readiness_status(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _cultivation(context, engine)
    metrc = resolve_trusted_regulatory_metrc(context=context, engine=engine, settings=settings, facility_capability="cultivation")
    environment = metrc.environment if metrc.configured else "sandbox"
    result = MetrcProcessReadinessService(engine).readiness_summary(context.organization_id, context.facility_id, environment=environment)
    return {
        **result,
        "configured": metrc.configured,
        "license_number": metrc.license_number if metrc.configured else "",
        "jurisdiction_code": metrc.state.upper() if metrc.configured else "",
        "message": metrc.message,
    }


@router.post("/tags/sync")
def sync_tags(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    _cultivation(context, engine)
    metrc = resolve_trusted_regulatory_metrc(context=context, engine=engine, settings=settings, facility_capability="cultivation")
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    common = {
        "state": metrc.state,
        "user_api_key": metrc.user_api_key,
        "integrator_api_key": metrc.integrator_api_key,
        "license_number": metrc.license_number,
        "environment": metrc.environment,
    }
    plant_result = fetch_all_available_plant_tags(**common)
    package_result = fetch_all_available_package_tags(**common)
    return MetrcProcessReadinessService(engine).sync_available_tags(
        context.organization_id,
        context.facility_id,
        jurisdiction_code=metrc.state,
        license_number=metrc.license_number,
        environment=metrc.environment,
        plant_records=_records(plant_result, "Metrc plant-tag sync failed."),
        package_records=_records(package_result, "Metrc package-tag sync failed."),
    )


@router.get("/tags")
def tags(
    tag_type: str = Query(default="", pattern="^(|plant|package)$"),
    status: str = Query(default="available", pattern="^(|available|reserved|used|voided)$"),
    environment: str = Query(default="sandbox", pattern="^(sandbox|production)$"),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _cultivation(context, engine)
    return {"items": MetrcProcessReadinessService(engine).list_tags(
        context.organization_id, context.facility_id, environment=environment, tag_type=tag_type, status=status
    )}


@router.post("/cultivation/immature-groups", status_code=201)
def create_immature_group(payload: ImmatureGroupCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        return MetrcProcessReadinessService(engine).create_immature_group(
            context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/groups/{group_id}/vegetative")
def assign_vegetative_tags(
    group_id: str,
    payload: VegetativeTagAssignment,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context); _cultivation(context, engine)
    metrc = resolve_trusted_regulatory_metrc(context=context, engine=engine, settings=settings, facility_capability="cultivation")
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    try:
        return MetrcProcessReadinessService(engine).assign_vegetative_tags(
            context.organization_id, context.facility_id, group_id,
            environment=metrc.environment, actor=context.user_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/plants/{plant_id}/replace-tag")
def replace_tag(
    plant_id: str,
    payload: TagReplacement,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context); _cultivation(context, engine)
    metrc = resolve_trusted_regulatory_metrc(context=context, engine=engine, settings=settings, facility_capability="cultivation")
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    try:
        return MetrcProcessReadinessService(engine).replace_plant_tag(
            context.organization_id, context.facility_id, plant_id,
            environment=metrc.environment, actor=context.user_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/plants/{plant_id}/correct-strain")
def correct_strain(plant_id: str, payload: StrainCorrection, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        return MetrcProcessReadinessService(engine).correct_plant_strain(
            context.organization_id, context.facility_id, plant_id, actor=context.user_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/harvests/{harvest_id}/wet-weights")
def harvest_wet_weights(harvest_id: str, payload: HarvestWeights, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        return MetrcProcessReadinessService(engine).record_harvest_wet_weights(
            context.organization_id, context.facility_id, harvest_id,
            plant_weights=[row.model_dump() for row in payload.plant_weights], actor=context.user_id,
            provider_confirmed=payload.provider_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/waste", status_code=201)
def record_waste(payload: WasteCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        data = payload.model_dump(); provider_confirmed = data.pop("provider_confirmed")
        return MetrcProcessReadinessService(engine).record_waste(
            context.organization_id, context.facility_id, actor=context.user_id,
            provider_confirmed=provider_confirmed, **data,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/manicure", status_code=201)
def manicure(payload: ManicureCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        data = payload.model_dump(); data["plant_weights"] = [row.model_dump() for row in payload.plant_weights]
        return MetrcProcessReadinessService(engine).create_manicure_batch(
            context.organization_id, context.facility_id, actor=context.user_id, **data
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/additives", status_code=201)
def additive(payload: AdditiveCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        return MetrcProcessReadinessService(engine).record_additive(
            context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/test-samples", status_code=201)
def test_sample(
    payload: TestSampleCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context); _cultivation(context, engine)
    metrc = resolve_trusted_regulatory_metrc(context=context, engine=engine, settings=settings, facility_capability="cultivation")
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    try:
        return MetrcProcessReadinessService(engine).create_test_sample(
            context.organization_id, context.facility_id, environment=metrc.environment,
            actor=context.user_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/test-samples/{sample_id}/confirm")
def confirm_test_sample(sample_id: str, payload: TestSampleConfirm, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _cultivation(context, engine)
    try:
        return MetrcProcessReadinessService(engine).confirm_test_sample(
            context.organization_id, context.facility_id, sample_id,
            provider_reference=payload.provider_reference, actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/transfers/whole-packages", status_code=201)
def dispatch_whole_packages(payload: WholePackageTransferCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _inventory(context, engine)
    if not payload.state_transfer_confirmed:
        raise HTTPException(422, "Confirm the Metrc manifest/transfer before posting the strict whole-package transfer in DoobieLogic.")
    try:
        return MetrcTransferReadinessService(engine).dispatch_whole_packages(
            context.organization_id, context.facility_id,
            destination_facility_id=payload.destination_facility_id,
            manifest_reference=payload.manifest_reference,
            provider_transfer_id=payload.provider_transfer_id,
            lines=[row.model_dump() for row in payload.lines],
            notes=payload.notes,
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/transfers/{transfer_id}/departure")
def departure(transfer_id: str, payload: TransferDeparture, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _inventory(context, engine)
    if not payload.state_departure_confirmed:
        raise HTTPException(422, "Confirm actual departure before locking the transfer lifecycle.")
    try:
        return MetrcTransferReadinessService(engine).confirm_departure(
            context.organization_id, context.facility_id, transfer_id, actor=context.user_id
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/transfers/{transfer_id}/lines/{line_id}/receive")
def receive_whole_package(transfer_id: str, line_id: str, payload: TransferReceive, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); require_inventory_operation_capability(context, engine, payload.operation)
    if not payload.state_receipt_confirmed:
        raise HTTPException(422, "Confirm this exact manifested package was received in Metrc before posting destination inventory.")
    try:
        return MetrcTransferReadinessService(engine).receive_whole_package(
            context.organization_id, context.facility_id, transfer_id, line_id,
            operation=payload.operation, actor=context.user_id, lot_code=payload.lot_code,
            location=payload.location, notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/transfers/{transfer_id}/lines/{line_id}/reject")
def reject_package(transfer_id: str, line_id: str, payload: TransferReject, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _inventory(context, engine)
    if not payload.state_rejection_confirmed:
        raise HTTPException(422, "Confirm the package rejection in Metrc before recording the rejected/returning state locally.")
    try:
        return MetrcTransferReadinessService(engine).reject_package(
            context.organization_id, context.facility_id, transfer_id, line_id,
            actor=context.user_id, reason=payload.reason, notes=payload.notes,
            return_manifest_reference=payload.return_manifest_reference,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/transfers/{transfer_id}/lines/{line_id}/return")
def receive_return(transfer_id: str, line_id: str, payload: TransferReturn, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _write(context); _inventory(context, engine)
    try:
        return MetrcTransferReadinessService(engine).receive_rejected_return(
            context.organization_id, context.facility_id, transfer_id, line_id,
            actor=context.user_id, state_return_confirmed=payload.state_return_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
