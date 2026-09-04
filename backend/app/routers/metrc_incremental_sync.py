from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.metrc_incremental_sync import MetrcIncrementalSyncService
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import resolve_metrc_context


router = APIRouter()


@router.post("/metrc/incremental-sync")
def incremental_metrc_sync(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Apply documented LastModified deltas for the active verified facility.

    The active RequestContext is the facility scope. The credential, provider
    environment and RegulatoryFacilityMapping must all agree before any provider
    request is allowed. This route does not accept a caller-supplied license that
    could be used to cross facility boundaries.
    """

    if context.role.casefold() not in {"dev", "admin"}:
        raise HTTPException(403, "DEV or Admin access is required to synchronize Metrc provider state.")

    try:
        _service, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not metrc.configured:
        raise HTTPException(422, metrc.message or "Configure Metrc for this facility before synchronizing.")
    if not metrc.trusted_mapping or metrc.mapping is None:
        raise HTTPException(409, "Verify the exact Metrc facility/license mapping before incremental synchronization.")
    if metrc.mapping.organization_id != context.organization_id or metrc.mapping.facility_id != context.facility_id:
        raise HTTPException(409, "The verified Metrc mapping does not belong to the active DoobieLogic facility.")
    if metrc.mapping.license_number != metrc.license_number or metrc.mapping.environment != metrc.environment:
        raise HTTPException(409, "The saved Metrc credential and verified facility mapping no longer have the same license/environment scope.")

    result = MetrcIncrementalSyncService(engine).sync(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        state=metrc.state,
        environment=metrc.environment,
        license_number=metrc.license_number,
        integrator_api_key=metrc.integrator_api_key,
        user_api_key=metrc.user_api_key,
        actor=context.user_id,
    )
    return {
        "ok": result["totals"]["failed"] == 0,
        "incremental": result,
        "message": (
            "Metrc changed-record synchronization completed. Omitted delta rows were not treated as removals; a periodic full snapshot remains authoritative for active membership."
        ),
    }
