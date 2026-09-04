from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.metrc_evaluation_lifecycle import LIFECYCLE_EVALUATION_ACTIONS

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_harvest_actions import (
    MetrcHarvestActionError,
    MetrcHarvestActionService,
    PROMOTED_HARVEST_ACTIONS,
    harvest_confirmation_token,
)
from ..services.metrc_harvest_operator_service import MetrcHarvestOperatorService
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc


router = APIRouter(prefix="/metrc-harvest", tags=["metrc-harvest"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow controlled harvest traceability changes.")


def _metrc(context: RequestContext, engine: Engine, settings: Settings):
    require_facility_capability(context, engine, "cultivation")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="cultivation",
    )
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    if str(metrc.state or "").strip().upper() != "MA" or str(metrc.environment or "").strip().casefold() != "sandbox":
        raise HTTPException(409, "Promoted harvest writes are currently restricted to the verified Massachusetts Metrc sandbox.")
    return metrc


class HarvestPlantWeight(BaseModel):
    plant_id: str = Field(min_length=1, max_length=64)
    wet_weight_g: float = Field(ge=0)


class HarvestActionRequest(BaseModel):
    operation_type: Literal["harvest_start", "harvest_waste", "harvest_finish", "harvest_unfinish"]
    harvest_id: str = Field(min_length=1, max_length=64)
    actual_date: date = Field(default_factory=date.today)
    plant_weights: list[HarvestPlantWeight] = Field(default_factory=list, max_length=5000)
    drying_room_id: str = Field(default="", max_length=64)
    waste_type: str = Field(default="", max_length=120)
    waste_weight_g: float = Field(default=0.0, ge=0)
    waste_method: str = Field(default="", max_length=255)
    waste_reason: str = Field(default="", max_length=255)
    waste_location: str = Field(default="", max_length=160)
    measurement_basis: Literal["", "wet", "dry"] = ""
    all_waste_reported: bool = False
    reason: str = Field(default="Harvest Metrc synchronization", min_length=3, max_length=255)


class HarvestActionExecute(HarvestActionRequest):
    confirmation_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=32, max_length=128)


def _kwargs(payload: HarvestActionRequest) -> dict[str, Any]:
    return {
        "operation_type": payload.operation_type,
        "harvest_id": payload.harvest_id,
        "actual_date": payload.actual_date.isoformat(),
        "plant_weights": [row.model_dump() for row in payload.plant_weights],
        "drying_room_id": payload.drying_room_id,
        "waste_type": payload.waste_type,
        "waste_weight_g": payload.waste_weight_g,
        "waste_method": payload.waste_method,
        "waste_reason": payload.waste_reason,
        "waste_location": payload.waste_location,
        "measurement_basis": payload.measurement_basis,
        "all_waste_reported": payload.all_waste_reported,
        "reason": payload.reason,
    }


@router.get("/status")
def harvest_action_status(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    return {
        "ready": True,
        "provider": "metrc",
        "jurisdiction_code": str(metrc.state).upper(),
        "environment": metrc.environment,
        "license_number": metrc.license_number,
        "promoted_actions": sorted(PROMOTED_HARVEST_ACTIONS),
        "execution_boundary": "Start harvest is a reviewed composite of individually verified plant writes, not a provider-atomic operation. Partial/unknown provider outcomes stop immediately in reconciliation.",
    }


@router.post("/actions/preview")
def preview_harvest_action(
    payload: HarvestActionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        prepared = MetrcHarvestActionService(engine).prepare(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            **_kwargs(payload),
        )
        confirmation_id = str(uuid4())
        token = harvest_confirmation_token(
            prepared=prepared,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            confirmation_id=confirmation_id,
        )
        spec = LIFECYCLE_EVALUATION_ACTIONS[prepared["evaluator_operation"]]
        return {
            "ready": True,
            "operation_type": prepared["operation_type"],
            "summary": prepared["summary"],
            "confirmation_id": confirmation_id,
            "confirmation_token": token,
            "compliance_evidence": {
                "method": spec.method,
                "path": spec.path,
                "license_number": metrc.license_number,
                "environment": metrc.environment,
                "provider_request_body": prepared["provider_request_body"],
                "provider_atomic": prepared["operation_type"] != "harvest_start",
            },
            "message": (
                "Review every plant weight and the drying location. Metrc harvest start executes one verified plant row at a time; any partial/unknown provider state stops in reconciliation."
                if prepared["operation_type"] == "harvest_start"
                else "Review the harvest business values before confirming. Any local or Metrc state change invalidates this confirmation."
            ),
        }
    except MetrcHarvestActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/execute")
def execute_harvest_action(
    payload: HarvestActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        return MetrcHarvestOperatorService(engine).execute(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            confirmation_id=payload.confirmation_id,
            confirmation_token=payload.confirmation_token,
            **_kwargs(payload),
        )
    except MetrcHarvestActionError as exc:
        raise HTTPException(422, str(exc)) from exc
