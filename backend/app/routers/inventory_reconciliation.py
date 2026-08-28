from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.metrc_reconciliation import fetch_all_active_metrc_packages
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.inventory_reconciliation import InventoryMetrcReconciliationService
from .inventory import _metrc_context


router = APIRouter(prefix="/inventory", tags=["inventory-reconciliation"])


@router.get("/{operation}/reconciliation")
def reconcile_inventory_with_metrc(
    operation: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    normalized = str(operation or "").strip().casefold()
    metrc = _metrc_context(
        context=context,
        engine=engine,
        settings=settings,
        operation=normalized,
    )
    if not metrc.configured:
        return {
            "configured": False,
            "ready": False,
            "operation": normalized,
            "provider": "metrc",
            "read_only": True,
            "message": metrc.message,
            "summary": {
                "status": "unavailable",
                "local_tracked_lot_count": 0,
                "metrc_package_count": 0,
                "matched_package_count": 0,
                "discrepancy_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "info_count": 0,
                "untracked_local_lot_count": 0,
                "ignored_metrc_record_count": 0,
                "by_code": {},
            },
            "discrepancies": [],
        }

    result = fetch_all_active_metrc_packages(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
        environment=metrc.environment,
    )
    if not result.get("ok"):
        status = 409 if result.get("status") == "regulatory_read_blocked" else 502
        raise HTTPException(status, str(result.get("message") or "Metrc active package request failed."))

    read_plan = result.get("read_plan") if isinstance(result.get("read_plan"), dict) else {}
    evidence = read_plan.get("evidence") if isinstance(read_plan, dict) else None
    report = InventoryMetrcReconciliationService(engine).reconcile(
        context.organization_id,
        context.facility_id,
        jurisdiction_code=metrc.state.upper(),
        license_number=metrc.license_number,
        environment=metrc.environment,
        metrc_records=[dict(row) for row in result.get("records") or [] if isinstance(row, dict)],
        evidence=evidence if isinstance(evidence, dict) else None,
    )
    return {
        "configured": True,
        "ready": True,
        "operation": normalized,
        "message": "Read-only Metrc reconciliation completed against the active facility package ledger.",
        "page_count": int(result.get("page_count") or 1),
        "truncated": bool(result.get("truncated")),
        **report,
    }
