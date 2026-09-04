from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import LIFECYCLE_EVALUATION_ACTIONS
from services.metrc_production import fetch_all_available_plant_tags

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_cultivation_actions import (
    MetrcCultivationActionError,
    MetrcCultivationActionService,
    PROMOTED_CULTIVATION_ACTIONS,
    cultivation_confirmation_token,
)
from ..services.metrc_cultivation_identity import (
    MetrcCultivationIdentityError,
    MetrcCultivationIdentityService,
)
from ..services.metrc_cultivation_tags import MetrcCultivationTagMirror
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc


router = APIRouter(prefix="/metrc-cultivation", tags=["metrc-cultivation"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow controlled cultivation traceability changes.")


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
        raise HTTPException(409, "Promoted cultivation writes are currently restricted to the verified Massachusetts Metrc sandbox.")
    return metrc


def _refresh_plant_tag_snapshot(context: RequestContext, engine: Engine, metrc) -> dict[str, Any]:
    result = fetch_all_available_plant_tags(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
        environment=metrc.environment,
    )
    if not result.get("ok"):
        raise HTTPException(502, str(result.get("message") or "Fresh Metrc available plant-tag lookup failed."))
    records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
    try:
        return MetrcCultivationTagMirror(engine).replace_available_plant_snapshot(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            jurisdiction_code=metrc.state,
            license_number=metrc.license_number,
            environment=metrc.environment,
            records=records,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class RoomLinkRequest(BaseModel):
    provider_location_id: str = Field(min_length=1, max_length=64)


class CultivationActionRequest(BaseModel):
    operation_type: Literal["plant_batch_sync", "plant_batch_vegetative", "plant_move"]
    entity_id: str = Field(min_length=1, max_length=64)
    actual_date: date = Field(default_factory=date.today)
    destination_room_id: str = Field(default="", max_length=64)
    starting_tag: str = Field(default="", max_length=64)
    reason: str = Field(default="Cultivation Metrc synchronization", min_length=3, max_length=255)


class CultivationActionExecute(CultivationActionRequest):
    confirmation_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=32, max_length=128)


def _action_kwargs(payload: CultivationActionRequest) -> dict[str, Any]:
    return {
        "operation_type": payload.operation_type,
        "entity_id": payload.entity_id,
        "actual_date": payload.actual_date.isoformat(),
        "destination_room_id": payload.destination_room_id,
        "starting_tag": payload.starting_tag,
        "reason": payload.reason,
    }


@router.get("/status")
def cultivation_action_status(
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
        "promoted_actions": sorted(PROMOTED_CULTIVATION_ACTIONS),
        "execution_boundary": "Preview binds current local state, exact regulatory identities, exact provider payload, facility/license, and current provider readback. Execution recomputes that state and fails closed if it changed.",
    }


@router.get("/identities")
def cultivation_identities(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    return {
        "environment": metrc.environment,
        "license_number": metrc.license_number,
        **MetrcCultivationIdentityService(engine).list_links(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            environment=metrc.environment,
        ),
    }


@router.get("/locations")
def cultivation_metrc_locations(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Explicit operator-triggered bounded Metrc location lookup for room linking."""

    metrc = _metrc(context, engine, settings)
    rows: list[dict[str, Any]] = []
    max_pages = 20
    page_size = 50
    for page_number in range(1, max_pages + 1):
        result = fetch_metrc_resource(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            resource="locations_active",
            environment=metrc.environment,
            license_number=metrc.license_number,
            page_size=page_size,
            page_number=page_number,
        )
        if not result.get("ok"):
            raise HTTPException(502, str(result.get("message") or "Metrc active-location lookup failed."))
        page = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
        rows.extend(page)
        if len(page) < page_size:
            break
    return {
        "items": [
            {
                "provider_id": str(row.get("provider_id") or ""),
                "name": str(row.get("name") or ""),
                "status": str(row.get("status") or ""),
                "last_modified": str(row.get("last_modified") or ""),
            }
            for row in rows
            if str(row.get("provider_id") or "").strip()
        ],
        "truncated": len(rows) >= max_pages * page_size,
        "page_size": page_size,
        "max_pages": max_pages,
    }


@router.post("/rooms/{room_id}/link")
def link_cultivation_room(
    room_id: str,
    payload: RoomLinkRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        return MetrcCultivationIdentityService(engine).link_room(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            room_id=room_id,
            provider_location_id=payload.provider_location_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
        )
    except MetrcCultivationIdentityError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/preview")
def preview_cultivation_action(
    payload: CultivationActionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    if payload.operation_type == "plant_batch_vegetative":
        _refresh_plant_tag_snapshot(context, engine, metrc)
    service = MetrcCultivationActionService(engine)
    try:
        prepared = service.prepare(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            **_action_kwargs(payload),
        )
        confirmation_id = str(uuid4())
        token = cultivation_confirmation_token(
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
            },
            "message": "Review the business values shown before confirming. Any local or Metrc state change invalidates this confirmation.",
        }
    except MetrcCultivationActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/execute")
def execute_cultivation_action(
    payload: CultivationActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    if payload.operation_type == "plant_batch_vegetative":
        _refresh_plant_tag_snapshot(context, engine, metrc)
    try:
        return MetrcCultivationActionService(engine).execute(
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
            **_action_kwargs(payload),
        )
    except MetrcCultivationActionError as exc:
        raise HTTPException(422, str(exc)) from exc