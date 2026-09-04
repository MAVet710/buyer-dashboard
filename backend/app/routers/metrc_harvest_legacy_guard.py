from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.cultivation.service import CultivationService
from modules.regulatory.metrc_guide_v11 import MetrcGuideV11Service

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..schemas.plants import CultivationHarvestTransition
from ..services.cultivation_regulatory_guard import CultivationRegulatoryGuard


router = APIRouter(tags=["metrc-harvest-guard"])
WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow this cultivation change.")


def _cultivation(context: RequestContext, engine: Engine) -> None:
    require_facility_capability(context, engine, "cultivation")


def _governed_required(action: str) -> None:
    raise HTTPException(
        409,
        f"{action} can no longer be confirmed manually. Use the governed Harvest/Post-Harvest Metrc action so the provider write, fresh readback, reconciliation, and local commit are one audited workflow.",
    )


def _strict_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"true", "1", "yes", "y", "on"}:
            return True
        if token in {"false", "0", "no", "n", "off", ""}:
            return False
    raise ValueError("provider_confirmed must be a boolean value.")


@router.post("/metrc-readiness/cultivation/harvests/{harvest_id}/wet-weights")
def block_legacy_harvest_wet_weights(
    harvest_id: str,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context); _cultivation(context, engine)
    _governed_required("Starting a harvest / recording provider-confirmed wet weights")


@router.post("/metrc-readiness/cultivation/harvests/{harvest_id}/add-plants")
def block_legacy_add_harvest_plants(
    harvest_id: str,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context); _cultivation(context, engine)
    _governed_required("Adding forgotten plants to a Metrc harvest")


@router.post("/metrc-readiness/cultivation/harvests/{harvest_id}/finish")
def block_legacy_finish_harvest(
    harvest_id: str,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context); _cultivation(context, engine)
    _governed_required("Finishing a Metrc harvest")


@router.post("/metrc-readiness/cultivation/harvests/{harvest_id}/unfinish")
def block_legacy_unfinish_harvest(
    harvest_id: str,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context); _cultivation(context, engine)
    _governed_required("Reopening a Metrc harvest")


@router.post("/metrc-readiness/cultivation/harvests/{harvest_id}/discontinue")
def block_legacy_discontinue_harvest(
    harvest_id: str,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context); _cultivation(context, engine)
    _governed_required("Discontinuing/restoring a Metrc harvest")


@router.post("/metrc-readiness/cultivation/harvests/{harvest_id}/waste/{waste_id}/discontinue")
def block_legacy_discontinue_harvest_waste(
    harvest_id: str,
    waste_id: str,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _write(context); _cultivation(context, engine)
    _governed_required("Discontinuing a Metrc harvest waste record")


@router.post("/metrc-readiness/cultivation/waste", status_code=201)
def guarded_legacy_waste(
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Preserve plant/group legacy waste, but harvest waste must use governed Metrc execution."""

    _write(context); _cultivation(context, engine)
    target_type = str(payload.get("target_type") or "").strip().casefold()
    if target_type == "harvest":
        _governed_required("Recording Metrc harvest waste")
    try:
        data = dict(payload)
        provider_confirmed = _strict_bool(data.pop("provider_confirmed", False))
        return MetrcGuideV11Service(engine).record_waste(
            context.organization_id,
            context.facility_id,
            actor=context.user_id,
            provider_confirmed=provider_confirmed,
            **data,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/inventory/production/plants/harvests/{harvest_id}/transition")
def guarded_local_harvest_transition(
    harvest_id: str,
    payload: CultivationHarvestTransition,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Keep untracked local Harvest 360 usable; fail closed after Metrc control begins."""

    _write(context); _cultivation(context, engine)
    try:
        CultivationRegulatoryGuard(engine).require_local_only_allowed(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_type="cultivation_harvest",
            entity_ids=[harvest_id],
            action_label="This harvest status/weight change",
        )
        return CultivationService(engine).transition_harvest(
            context.organization_id,
            context.facility_id,
            harvest_id,
            actor=context.user_id,
            **payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
