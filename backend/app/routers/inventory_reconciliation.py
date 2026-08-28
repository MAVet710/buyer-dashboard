from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.metrc_production import fetch_all_active_processing_jobs
from services.metrc_reconciliation import fetch_all_active_metrc_packages
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.inventory_reconciliation import InventoryMetrcReconciliationService
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc
from .inventory import _metrc_context


router = APIRouter(prefix="/inventory", tags=["inventory-reconciliation"])


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


@router.get("/production/regulatory/manufacturing")
def manufacturing_regulatory_snapshot(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Read the exact manufacturing license's active package/process state."""

    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="production",
    )
    if not metrc.configured:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "scope": "manufacturing",
            "read_only": True,
            "message": metrc.message,
            "resources": {},
        }

    common = {
        "state": metrc.state,
        "user_api_key": metrc.user_api_key,
        "integrator_api_key": metrc.integrator_api_key,
        "license_number": metrc.license_number,
        "environment": metrc.environment,
    }
    packages = fetch_all_active_metrc_packages(**common)
    processing = fetch_all_active_processing_jobs(**common)
    _raise_resource_error(packages, "Metrc active package request failed.")
    _raise_resource_error(processing, "Metrc active processing request failed.")

    package_view = _resource_view(packages)
    processing_view = _resource_view(processing)
    return {
        "configured": True,
        "ready": True,
        "provider": "metrc",
        "scope": "manufacturing",
        "jurisdiction_code": metrc.state.upper(),
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "read_only": True,
        "message": "Manufacturing regulatory state loaded from the verified Metrc facility mapping.",
        "summary": {
            "active_package_count": package_view["count"],
            "active_processing_job_count": processing_view["count"],
        },
        "resources": {
            "packages": package_view,
            "processing_jobs": processing_view,
        },
    }
