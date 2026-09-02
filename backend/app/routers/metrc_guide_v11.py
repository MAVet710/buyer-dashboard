from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.regulatory.metrc_guide_v11 import MetrcGuideV11Service, MetrcGuideV11TransferService

from ..auth import RequestContext, get_request_context, require_facility_capability, require_inventory_operation_capability
from ..database import get_engine


router = APIRouter(prefix="/metrc-readiness", tags=["metrc-readiness-guide-v11"])
WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow this Metrc-aligned operational change.")


def _cultivation(context: RequestContext, engine: Engine) -> None:
    require_facility_capability(context, engine, "cultivation")


class HarvestPlantWeight(BaseModel):
    plant_id: str = Field(min_length=1, max_length=64)
    wet_weight_g: float = Field(ge=0)


class HarvestAddPlants(BaseModel):
    plant_weights: list[HarvestPlantWeight] = Field(min_length=1, max_length=5000)
    harvest_date: date
    provider_confirmed: bool = False


class HarvestFinish(BaseModel):
    provider_confirmed: bool = False
    all_waste_reported: bool = False


class HarvestUnfinish(BaseModel):
    provider_confirmed: bool = False
    provider_reference: str = Field(default="", max_length=255)


class HarvestWasteDiscontinue(BaseModel):
    provider_confirmed: bool = False
    provider_reference: str = Field(default="", max_length=255)


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
    measurement_basis: Literal["wet", "dry"] | None = None
    notes: str = Field(default="", max_length=4000)
    provider_confirmed: bool = False


class TransferReceive(BaseModel):
    operation: Literal["retail", "production"]
    state_receipt_confirmed: bool = False
    received_quantity: float | None = Field(default=None, gt=0)
    received_unit: str = Field(default="", max_length=32)
    variance_reason: Literal["", "scale_variance", "uom_conversion"] = ""
    lot_code: str = Field(default="", max_length=255)
    location: str = Field(default="RECEIVING", max_length=160)
    notes: str = Field(default="", max_length=4000)


@router.post("/cultivation/harvests/{harvest_id}/add-plants")
def harvest_add_plants(
    harvest_id: str,
    payload: HarvestAddPlants,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context)
    _cultivation(context, engine)
    try:
        return MetrcGuideV11Service(engine).add_plants_to_harvest(
            context.organization_id,
            context.facility_id,
            harvest_id,
            plant_weights=[row.model_dump() for row in payload.plant_weights],
            harvest_date=payload.harvest_date,
            actor=context.user_id,
            provider_confirmed=payload.provider_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/cultivation/harvests/{harvest_id}/closeout")
def harvest_closeout(
    harvest_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _cultivation(context, engine)
    try:
        return MetrcGuideV11Service(engine).harvest_closeout_preview(
            context.organization_id, context.facility_id, harvest_id
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/harvests/{harvest_id}/finish")
def harvest_finish(
    harvest_id: str,
    payload: HarvestFinish,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context)
    _cultivation(context, engine)
    try:
        return MetrcGuideV11Service(engine).finish_harvest(
            context.organization_id,
            context.facility_id,
            harvest_id,
            actor=context.user_id,
            provider_confirmed=payload.provider_confirmed,
            all_waste_reported=payload.all_waste_reported,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/harvests/{harvest_id}/unfinish")
def harvest_unfinish(
    harvest_id: str,
    payload: HarvestUnfinish,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context)
    _cultivation(context, engine)
    try:
        return MetrcGuideV11Service(engine).unfinish_harvest(
            context.organization_id,
            context.facility_id,
            harvest_id,
            actor=context.user_id,
            provider_confirmed=payload.provider_confirmed,
            provider_reference=payload.provider_reference,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/waste", status_code=201)
def record_waste(
    payload: WasteCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context)
    _cultivation(context, engine)
    try:
        data = payload.model_dump()
        provider_confirmed = data.pop("provider_confirmed")
        return MetrcGuideV11Service(engine).record_waste(
            context.organization_id,
            context.facility_id,
            actor=context.user_id,
            provider_confirmed=provider_confirmed,
            **data,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cultivation/harvests/{harvest_id}/waste/{waste_id}/discontinue")
def discontinue_harvest_waste(
    harvest_id: str,
    waste_id: str,
    payload: HarvestWasteDiscontinue,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context)
    _cultivation(context, engine)
    try:
        return MetrcGuideV11Service(engine).discontinue_harvest_waste(
            context.organization_id,
            context.facility_id,
            harvest_id,
            waste_id,
            actor=context.user_id,
            provider_confirmed=payload.provider_confirmed,
            provider_reference=payload.provider_reference,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/transfers/{transfer_id}/lines/{line_id}/receive")
def receive_manifested_package(
    transfer_id: str,
    line_id: str,
    payload: TransferReceive,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context)
    require_inventory_operation_capability(context, engine, payload.operation)
    if not payload.state_receipt_confirmed:
        raise HTTPException(422, "Confirm this exact manifested package was received in Metrc before posting destination inventory.")
    try:
        return MetrcGuideV11TransferService(engine).receive_manifested_package(
            context.organization_id,
            context.facility_id,
            transfer_id,
            line_id,
            operation=payload.operation,
            actor=context.user_id,
            received_quantity=payload.received_quantity,
            received_unit=payload.received_unit,
            variance_reason=payload.variance_reason,
            lot_code=payload.lot_code,
            location=payload.location,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
