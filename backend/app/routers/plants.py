from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from modules.cultivation.service import CultivationService
from services.metrc_production import (
    fetch_all_active_harvests,
    fetch_all_active_plant_batches,
    fetch_all_flowering_plants,
    fetch_all_vegetative_plants,
)
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..schemas.plants import PlantCreate, PlantEventItem, PlantItem, PlantTransition
from ..services.cultivation_reconciliation import CultivationMetrcReconciliationService
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc

router = APIRouter(prefix="/inventory/production/plants", tags=["cultivation"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}


def item(plant) -> PlantItem:
    return PlantItem.model_validate({column: getattr(plant, column) for column in PlantItem.model_fields})


def require_write(context: RequestContext):
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow cultivation changes.")


def require_cultivation(context: RequestContext, engine: Engine):
    # Cultivation is its own legal license context. A cultivation-only facility
    # uses shared Production Ops inventory but must not be forced to also claim
    # a manufacturing/production capability just to manage its plants.
    require_facility_capability(context, engine, "cultivation")


def _resource_view(result: dict[str, Any], *, limit: int = 100) -> dict[str, Any]:
    records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
    read_plan = result.get("read_plan") if isinstance(result.get("read_plan"), dict) else {}
    return {
        "resource": str(result.get("resource") or ""),
        "capability": str(result.get("capability") or ""),
        "count": len(records),
        "page_count": int(result.get("page_count") or 1),
        "truncated": bool(result.get("truncated")),
        "records_truncated": len(records) > limit,
        "evidence": read_plan.get("evidence") if isinstance(read_plan, dict) else None,
        "records": [
            {
                key: row.get(key)
                for key in (
                    "provider_id",
                    "label",
                    "name",
                    "status",
                    "quantity",
                    "unit_of_measure",
                    "last_modified",
                )
            }
            for row in records[:limit]
        ],
    }


def _raise_resource_error(result: dict[str, Any], fallback: str) -> None:
    if result.get("ok"):
        return
    status = 409 if result.get("status") == "regulatory_read_blocked" else 502
    raise HTTPException(status, str(result.get("message") or fallback))


@router.get("", response_model=list[PlantItem])
def list_plants(
    phase: str = "",
    room: str = "",
    search: str = Query(default="", max_length=200),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_cultivation(context, engine)
    return [
        item(row)
        for row in CultivationService(engine).list_plants(
            context.organization_id, context.facility_id, phase, room, search
        )
    ]


@router.get("/regulatory")
def cultivation_regulatory_snapshot(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Read and reconcile the exact cultivation license's active Metrc state."""

    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="cultivation",
    )
    if not metrc.configured:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "scope": "cultivation",
            "read_only": True,
            "message": metrc.message,
            "resources": {},
            "reconciliation": None,
        }

    common = {
        "state": metrc.state,
        "user_api_key": metrc.user_api_key,
        "integrator_api_key": metrc.integrator_api_key,
        "license_number": metrc.license_number,
        "environment": metrc.environment,
    }
    batches = fetch_all_active_plant_batches(**common)
    vegetative = fetch_all_vegetative_plants(**common)
    flowering = fetch_all_flowering_plants(**common)
    harvests = fetch_all_active_harvests(**common)
    _raise_resource_error(batches, "Metrc active plant batch request failed.")
    _raise_resource_error(vegetative, "Metrc vegetative plant request failed.")
    _raise_resource_error(flowering, "Metrc flowering plant request failed.")
    _raise_resource_error(harvests, "Metrc active harvest request failed.")

    batch_view = _resource_view(batches)
    vegetative_view = _resource_view(vegetative)
    flowering_view = _resource_view(flowering)
    harvest_view = _resource_view(harvests)
    evidence = {
        "plant_batches": batch_view["evidence"],
        "vegetative_plants": vegetative_view["evidence"],
        "flowering_plants": flowering_view["evidence"],
        "harvests": harvest_view["evidence"],
    }
    reconciliation = CultivationMetrcReconciliationService(engine).reconcile(
        context.organization_id,
        context.facility_id,
        jurisdiction_code=metrc.state.upper(),
        license_number=metrc.license_number,
        environment=metrc.environment,
        vegetative_records=[
            dict(row) for row in vegetative.get("records") or [] if isinstance(row, dict)
        ],
        flowering_records=[
            dict(row) for row in flowering.get("records") or [] if isinstance(row, dict)
        ],
        evidence=evidence,
    )
    return {
        "configured": True,
        "ready": True,
        "provider": "metrc",
        "scope": "cultivation",
        "jurisdiction_code": metrc.state.upper(),
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "read_only": True,
        "message": "Cultivation regulatory state loaded from the verified Metrc facility mapping.",
        "summary": {
            "active_plant_batch_count": batch_view["count"],
            "vegetative_plant_count": vegetative_view["count"],
            "flowering_plant_count": flowering_view["count"],
            "active_harvest_count": harvest_view["count"],
        },
        "resources": {
            "plant_batches": batch_view,
            "vegetative_plants": vegetative_view,
            "flowering_plants": flowering_view,
            "harvests": harvest_view,
        },
        "reconciliation": reconciliation,
    }


@router.post("", response_model=PlantItem, status_code=201)
def create_plant(
    payload: PlantCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_write(context)
    require_cultivation(context, engine)
    try:
        return item(
            CultivationService(engine).create_plant(
                context.organization_id,
                context.facility_id,
                actor=context.user_id,
                **payload.model_dump(),
            )
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{plant_id}/transition", response_model=PlantItem)
def transition_plant(
    plant_id: str,
    payload: PlantTransition,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_write(context)
    require_cultivation(context, engine)
    try:
        return item(
            CultivationService(engine).transition(
                context.organization_id,
                context.facility_id,
                plant_id,
                actor=context.user_id,
                **payload.model_dump(),
            )
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{plant_id}/events", response_model=list[PlantEventItem])
def plant_events(
    plant_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_cultivation(context, engine)
    try:
        return [
            PlantEventItem.model_validate(
                {column: getattr(row, column) for column in PlantEventItem.model_fields}
            )
            for row in CultivationService(engine).events(
                context.organization_id, context.facility_id, plant_id
            )
        ]
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
