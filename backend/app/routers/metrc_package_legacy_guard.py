from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.traceability.object_links import TraceabilityObjectLinkRepository
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..schemas.inventory import InventoryAdjustmentCreate, InventoryAdjustmentResult
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc
from .inventory import adjust_inventory as legacy_adjust_inventory


router = APIRouter(prefix="/inventory", tags=["inventory-package-guard"])


@router.post("/{operation}/adjustments", response_model=InventoryAdjustmentResult, status_code=201)
def guarded_inventory_adjustment(
    operation: str,
    payload: InventoryAdjustmentCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Preserve local-only adjustment behavior but retire weaker Metrc sync once promoted."""

    operation_key = str(operation or "").strip().casefold()
    if operation_key not in {"production", "retail"}:
        return legacy_adjust_inventory(operation, payload, context, engine, settings)
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability=operation_key,
    )
    promoted = bool(
        metrc.configured
        and str(metrc.state or "").strip().upper() == "MA"
        and str(metrc.environment or "").strip().casefold() == "sandbox"
    )
    if not promoted:
        return legacy_adjust_inventory(operation, payload, context, engine, settings)

    if payload.sync_to_metrc:
        raise HTTPException(
            409,
            "The legacy tracked-adjustment path is retired for the promoted Massachusetts sandbox. Link the Product and package identities, then use the governed package adjustment workflow with fresh semantic readback.",
        )

    link = TraceabilityObjectLinkRepository(engine).get_local(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        provider="metrc",
        environment=str(metrc.environment or "").strip().casefold(),
        entity_type="inventory_lot",
        entity_id=payload.lot_id,
    )
    if link and link.provider_resource == "packages" and link.status in {"verified", "stale", "reconciliation_required"}:
        raise HTTPException(
            409,
            "This inventory lot is Metrc-tracked. Local-only quantity mutation is blocked; use the governed package adjustment workflow or reconcile the existing package identity first.",
        )
    return legacy_adjust_inventory(operation, payload, context, engine, settings)
