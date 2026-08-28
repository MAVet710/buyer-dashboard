from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.metrc_receiving import (
    fetch_all_delivery_packages,
    fetch_all_incoming_transfers,
    fetch_all_transfer_deliveries,
    fetch_metrc_lab_results,
)
from services.metrc_reconciliation import fetch_all_active_metrc_packages
from ..auth import RequestContext, get_request_context, require_inventory_operation_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.inventory_reconciliation import InventoryMetrcReconciliationService
from ..services.metrc_context import resolve_metrc_context


router = APIRouter(prefix="/inventory", tags=["inventory-regulatory"])
RECEIVING_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}


def _require_operation(operation: str) -> str:
    normalized = str(operation or "").strip().casefold()
    if normalized not in {"retail", "production"}:
        raise HTTPException(status_code=404, detail="Inventory operation not found.")
    return normalized


def _ready_metrc(
    *,
    operation: str,
    context: RequestContext,
    engine: Engine,
    settings: Settings,
    receiving: bool = False,
):
    normalized = _require_operation(operation)
    require_inventory_operation_capability(context, engine, normalized)
    if receiving and context.role.casefold() not in RECEIVING_ROLES:
        raise HTTPException(status_code=403, detail="Your role does not allow inventory receiving.")
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    credentials_present = bool(
        metrc.row
        and metrc.user_api_key
        and metrc.integrator_api_key
        and metrc.state
        and metrc.license_number
    )
    if not credentials_present:
        return normalized, metrc, False
    if metrc.status != "connected":
        raise HTTPException(
            status_code=409,
            detail="Validate the Metrc connection for this exact facility before loading live regulatory data.",
        )
    if not metrc.trusted_mapping:
        raise HTTPException(
            status_code=409,
            detail="An administrator must verify the exact Metrc facility, license, jurisdiction, credential, and environment mapping before live regulatory data can load.",
        )
    return normalized, metrc, True


def _transfer_row(item: dict) -> dict:
    return {
        "transfer_id": str(item.get("Id") or item.get("TransferId") or ""),
        "delivery_id": str(item.get("DeliveryId") or ""),
        "manifest": str(item.get("ManifestNumber") or ""),
        "vendor": str(item.get("ShipperFacilityName") or item.get("ShipperFacilityLicenseNumber") or ""),
        "vendor_license": str(item.get("ShipperFacilityLicenseNumber") or ""),
        "package_count": int(item.get("PackageCount") or item.get("DeliveryPackageCount") or 0),
        "received_count": int(item.get("ReceivedPackageCount") or item.get("DeliveryReceivedPackageCount") or 0),
        "estimated_arrival": str(item.get("EstimatedArrivalDateTime") or ""),
        "source": "Metrc",
    }


def _package_row(item: dict, delivery: dict) -> dict:
    shipped = float(item.get("ShippedQuantity") or item.get("Quantity") or 0.0)
    received = float(item.get("ReceivedQuantity") or 0.0)
    quantity = max(0.0, shipped - received) if shipped else received
    package_label = str(item.get("PackageLabel") or item.get("Label") or item.get("PackageTag") or "")
    return {
        "package_record_id": str(item.get("Id") or item.get("PackageId") or ""),
        "package_id": package_label,
        "item_id": str(item.get("ItemId") or ""),
        "item_name": str(item.get("ItemName") or item.get("ProductName") or item.get("Name") or ""),
        "category": str(item.get("ItemCategoryName") or item.get("CategoryName") or ""),
        "quantity": quantity,
        "shipped_quantity": shipped,
        "received_quantity": received,
        "unit": str(item.get("ShippedUnitOfMeasureName") or item.get("UnitOfMeasureName") or item.get("Unit") or "unit"),
        "shipment_state": str(item.get("ShipmentPackageState") or item.get("State") or ""),
        "lab_testing_state": str(item.get("LabTestingState") or item.get("LabTestResultStatus") or ""),
        "delivery_id": str(delivery.get("Id") or delivery.get("DeliveryId") or ""),
        "delivery_number": str(delivery.get("DeliveryNumber") or ""),
    }


# These GET routes deliberately shadow the older Inventory router when this
# router is registered first. The browser contract remains unchanged, while all
# live reads now require validated credentials plus the exact trusted mapping.
@router.get("/{operation}/inbound")
def trusted_inbound_queue(
    operation: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    normalized, metrc, ready = _ready_metrc(
        operation=operation,
        context=context,
        engine=engine,
        settings=settings,
        receiving=True,
    )
    if not ready:
        return {"configured": False, "message": metrc.message, "transfers": []}
    result = fetch_all_incoming_transfers(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
        environment=metrc.environment,
    )
    if not result.get("ok"):
        status = 409 if result.get("status") == "regulatory_read_blocked" else 502
        raise HTTPException(status, str(result.get("message") or "Metrc inbound transfer request failed."))
    transfers = [_transfer_row(row) for row in result.get("transfers") or []]
    return {
        "configured": True,
        "message": "Metrc inbound queue loaded through the verified facility mapping. State acceptance remains read-only and must still occur in Metrc.",
        "license_number": metrc.license_number,
        "environment": metrc.environment,
        "operation": normalized,
        "transfers": [row for row in transfers if row["transfer_id"]],
    }


@router.get("/{operation}/inbound/{transfer_id}")
def trusted_inbound_transfer_details(
    operation: str,
    transfer_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc, ready = _ready_metrc(
        operation=operation,
        context=context,
        engine=engine,
        settings=settings,
        receiving=True,
    )
    if not ready:
        raise HTTPException(422, metrc.message)
    deliveries_result = fetch_all_transfer_deliveries(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        transfer_id=transfer_id,
        environment=metrc.environment,
    )
    if not deliveries_result.get("ok"):
        status = 409 if deliveries_result.get("status") == "regulatory_read_blocked" else 502
        raise HTTPException(status, str(deliveries_result.get("message") or "Metrc transfer delivery request failed."))

    deliveries = list(deliveries_result.get("deliveries") or [])
    packages: list[dict] = []
    warnings: list[str] = []
    for delivery in deliveries:
        delivery_id = str(delivery.get("Id") or delivery.get("DeliveryId") or "").strip()
        if not delivery_id:
            warnings.append("One Metrc delivery had no delivery id and could not be expanded.")
            continue
        package_result = fetch_all_delivery_packages(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            delivery_id=delivery_id,
            environment=metrc.environment,
        )
        if not package_result.get("ok"):
            warnings.append(str(package_result.get("message") or f"Unable to load packages for delivery {delivery_id}."))
            continue
        packages.extend(_package_row(row, delivery) for row in package_result.get("packages") or [])
    return {
        "transfer_id": transfer_id,
        "deliveries": deliveries,
        "packages": packages,
        "warnings": warnings,
        "read_only_traceability": True,
        "environment": metrc.environment,
    }


@router.get("/{operation}/inbound/packages/{package_record_id}/lab-results")
def trusted_inbound_package_lab_results(
    operation: str,
    package_record_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _, metrc, ready = _ready_metrc(
        operation=operation,
        context=context,
        engine=engine,
        settings=settings,
        receiving=True,
    )
    if not ready:
        raise HTTPException(422, metrc.message)
    result = fetch_metrc_lab_results(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
        package_id=package_record_id,
        environment=metrc.environment,
    )
    if not result.get("ok"):
        status = 409 if result.get("status") == "regulatory_read_blocked" else 502
        raise HTTPException(status, str(result.get("message") or "Metrc lab result request failed."))
    return {
        "package_record_id": package_record_id,
        "lab_results": result.get("lab_results") or [],
        "read_only": True,
        "environment": metrc.environment,
    }


@router.get("/{operation}/reconciliation")
def reconcile_inventory_with_metrc(
    operation: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    normalized, metrc, ready = _ready_metrc(
        operation=operation,
        context=context,
        engine=engine,
        settings=settings,
    )
    if not ready:
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
