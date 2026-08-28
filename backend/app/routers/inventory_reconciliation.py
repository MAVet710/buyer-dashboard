from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.metrc_production import fetch_all_active_processing_jobs
from services.metrc_receiving import fetch_all_transfer_deliveries
from services.metrc_reconciliation import fetch_all_active_metrc_packages
from services.metrc_wholesale import (
    fetch_all_outgoing_transfer_templates,
    fetch_all_outgoing_transfers,
    fetch_all_transporter_drivers,
    fetch_all_transporter_vehicles,
    fetch_all_wholesale_delivery_packages,
)
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


def _optional_resource_view(result: dict[str, Any], *, fallback: str) -> dict[str, Any]:
    if result.get("ok"):
        return {"available": True, **_resource_view(result)}
    return {
        "available": False,
        "resource": str(result.get("resource") or ""),
        "status": str(result.get("status") or "unavailable"),
        "message": str(result.get("message") or fallback),
        "count": 0,
        "records": [],
        "evidence": None,
    }


def _source_string(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


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


@router.get("/wholesale/regulatory")
def wholesale_regulatory_snapshot(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Read the exact commercial license's outbound Metrc transport state.

    The snapshot expands at most 50 active outgoing transfers. This protects the
    operator from an accidental high-fanout request while still surfacing the
    transfer, manifest, delivery, wholesale-package, driver, and vehicle state
    needed to work current distribution operations.
    """

    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="commercial",
    )
    if not metrc.configured:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "scope": "wholesale",
            "read_only": True,
            "message": metrc.message,
            "resources": {},
            "transfers": [],
            "warnings": [],
        }

    common = {
        "state": metrc.state,
        "user_api_key": metrc.user_api_key,
        "integrator_api_key": metrc.integrator_api_key,
        "license_number": metrc.license_number,
        "environment": metrc.environment,
    }
    outgoing = fetch_all_outgoing_transfers(**common)
    _raise_resource_error(outgoing, "Metrc outgoing transfer request failed.")

    templates = fetch_all_outgoing_transfer_templates(**common)
    drivers = fetch_all_transporter_drivers(**common)
    vehicles = fetch_all_transporter_vehicles(**common)
    template_view = _optional_resource_view(templates, fallback="Metrc transfer templates are unavailable for this credential.")
    driver_view = _optional_resource_view(drivers, fallback="Metrc transporter drivers are unavailable for this credential.")
    vehicle_view = _optional_resource_view(vehicles, fallback="Metrc transporter vehicles are unavailable for this credential.")

    transfer_rows = [dict(row) for row in outgoing.get("rows") or [] if isinstance(row, dict)]
    expansion_limited = len(transfer_rows) > 50
    projected: list[dict[str, Any]] = []
    warnings: list[str] = []
    delivery_count = 0
    wholesale_package_count = 0
    manifest_count = 0

    for transfer in transfer_rows[:50]:
        transfer_id = _source_string(transfer, "Id", "TransferId")
        manifest = _source_string(transfer, "ManifestNumber", "Manifest", "ManifestNo")
        if manifest:
            manifest_count += 1
        transfer_view = {
            "transfer_id": transfer_id,
            "manifest_number": manifest,
            "status": _source_string(transfer, "Status", "State", "ShipmentTypeName"),
            "recipient": _source_string(transfer, "DestFacilityName", "RecipientFacilityName", "ReceiverFacilityName"),
            "recipient_license": _source_string(
                transfer,
                "DestFacilityLicenseNumber",
                "RecipientFacilityLicenseNumber",
                "ReceiverFacilityLicenseNumber",
            ),
            "created_at": _source_string(transfer, "CreatedDateTime", "CreatedAt", "LastModified"),
            "delivery_count": 0,
            "wholesale_package_count": 0,
        }
        if not transfer_id:
            warnings.append("One outgoing Metrc transfer had no transfer id and could not be expanded.")
            projected.append(transfer_view)
            continue

        deliveries = fetch_all_transfer_deliveries(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            transfer_id=transfer_id,
            environment=metrc.environment,
        )
        if not deliveries.get("ok"):
            warnings.append(str(deliveries.get("message") or f"Unable to load deliveries for transfer {transfer_id}."))
            projected.append(transfer_view)
            continue

        delivery_rows = [dict(row) for row in deliveries.get("rows") or [] if isinstance(row, dict)]
        transfer_view["delivery_count"] = len(delivery_rows)
        delivery_count += len(delivery_rows)
        for delivery in delivery_rows:
            delivery_id = _source_string(delivery, "Id", "DeliveryId")
            if not delivery_id:
                warnings.append(f"Transfer {transfer_id} included a delivery without an id.")
                continue
            packages = fetch_all_wholesale_delivery_packages(
                state=metrc.state,
                user_api_key=metrc.user_api_key,
                integrator_api_key=metrc.integrator_api_key,
                delivery_id=delivery_id,
                environment=metrc.environment,
            )
            if not packages.get("ok"):
                warnings.append(str(packages.get("message") or f"Unable to load wholesale packages for delivery {delivery_id}."))
                continue
            count = len([row for row in packages.get("rows") or [] if isinstance(row, dict)])
            transfer_view["wholesale_package_count"] += count
            wholesale_package_count += count
        projected.append(transfer_view)

    if expansion_limited:
        warnings.append("Only the first 50 outgoing transfers were expanded into deliveries and wholesale packages.")

    outgoing_plan = outgoing.get("read_plan") if isinstance(outgoing.get("read_plan"), dict) else {}
    return {
        "configured": True,
        "ready": True,
        "provider": "metrc",
        "scope": "wholesale",
        "jurisdiction_code": metrc.state.upper(),
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "read_only": True,
        "message": "Wholesale regulatory state loaded from the verified Metrc facility mapping.",
        "summary": {
            "outgoing_transfer_count": len(transfer_rows),
            "manifest_reference_count": manifest_count,
            "expanded_transfer_count": len(projected),
            "delivery_count": delivery_count,
            "wholesale_package_count": wholesale_package_count,
            "transfer_template_count": int(template_view.get("count") or 0),
            "transporter_driver_count": int(driver_view.get("count") or 0),
            "transporter_vehicle_count": int(vehicle_view.get("count") or 0),
            "expansion_limited": expansion_limited,
        },
        "evidence": outgoing_plan.get("evidence"),
        "resources": {
            "transfer_templates": template_view,
            "transporter_drivers": driver_view,
            "transporter_vehicles": vehicle_view,
        },
        "transfers": projected,
        "warnings": warnings[:100],
    }