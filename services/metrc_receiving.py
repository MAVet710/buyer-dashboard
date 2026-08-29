"""Read-only Metrc helpers used by Inventory receiving.

All functions in this module use GET endpoints only. DoobieLogic never accepts a
state transfer, edits a package, or releases lab results from the receiving UI.
Every page is planned through the verified regulatory capability layer before a
network request is made.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from modules.regulatory import RegulatoryReadError, build_metrc_read_plan, normalize_metrc_payload, payload_rows
from services.metrc_client import _metrc_get


PAGE_SIZE = 20
MAX_PAGES = 100


def _paged_resource_get(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    resource: str,
    environment: str = "production",
    license_number: str = "",
    path_parameters: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Read every available v2 page through one verified normalized resource."""

    rows: list[dict[str, Any]] = []
    first_result: dict[str, Any] | None = None
    page = 1
    total_pages = 1
    while page <= min(total_pages, MAX_PAGES):
        try:
            plan = build_metrc_read_plan(
                jurisdiction=state,
                resource=resource,
                environment=environment,
                license_number=license_number,
                path_parameters=path_parameters,
                query=query,
                page_size=PAGE_SIZE,
                page_number=page,
            )
        except RegulatoryReadError as exc:
            return {
                "ok": False,
                "status": "regulatory_read_blocked",
                "message": str(exc),
                "resource": resource,
            }

        result = _metrc_get(
            state=plan.jurisdiction_code,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            path=plan.path,
            params=plan.params,
            timeout_seconds=timeout_seconds,
        )
        result["read_plan"] = plan.public()
        result["resource"] = plan.resource
        result["capability"] = plan.capability
        if first_result is None:
            first_result = dict(result)
        if not result.get("ok"):
            return result
        payload = result.get("payload")
        rows.extend(payload_rows(payload))
        if isinstance(payload, dict):
            try:
                total_pages = max(1, int(payload.get("TotalPages") or payload.get("totalPages") or 1))
            except (TypeError, ValueError):
                total_pages = 1
        else:
            total_pages = 1
        page += 1

    output = first_result or {"ok": True, "status": "connected", "message": "Metrc request succeeded."}
    output["rows"] = rows
    output["records"] = normalize_metrc_payload(jurisdiction=state, resource=resource, payload=rows)
    output["page_count"] = min(total_pages, MAX_PAGES)
    output["truncated"] = total_pages > MAX_PAGES
    return output


def fetch_all_incoming_transfers(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    result = _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="incoming_transfers",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["transfers"] = list(result.get("rows") or [])
    return result


def fetch_all_transfer_deliveries(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    transfer_id: int | str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    result = _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="transfer_deliveries",
        environment=environment,
        path_parameters={"transfer_id": transfer_id},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["deliveries"] = list(result.get("rows") or [])
    return result


def fetch_all_delivery_packages(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    delivery_id: int | str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    result = _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="delivery_packages",
        environment=environment,
        path_parameters={"delivery_id": delivery_id},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["packages"] = list(result.get("rows") or [])
    return result


def fetch_metrc_lab_results(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    package_id: int | str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Retrieve lab test results for one package without changing Metrc."""

    package_id = str(package_id or "").strip()
    if not package_id:
        return {"ok": False, "status": "missing_package", "message": "A Metrc package id is required."}
    result = _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="lab_results",
        environment=environment,
        license_number=license_number,
        query={"packageId": package_id},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["lab_results"] = list(result.get("rows") or [])
    return result


def _decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        number = Decimal("0")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _transfer_id(row: dict[str, Any]) -> str:
    return str(row.get("Id") or row.get("TransferId") or "").strip()


def _canonical_inbound_package(row: dict[str, Any], delivery: dict[str, Any]) -> dict[str, str] | None:
    shipped = Decimal(_decimal_text(row.get("ShippedQuantity") or row.get("Quantity") or 0))
    received = Decimal(_decimal_text(row.get("ReceivedQuantity") or 0))
    remaining = max(Decimal("0"), shipped - received) if shipped else received
    if remaining <= 0:
        return None
    record_id = str(row.get("Id") or row.get("PackageId") or "").strip()
    package_label = str(row.get("PackageLabel") or row.get("Label") or row.get("PackageTag") or "").strip()
    identity = package_label or record_id
    if not identity:
        return None
    unit = str(row.get("ShippedUnitOfMeasureName") or row.get("UnitOfMeasureName") or row.get("Unit") or "unit").strip() or "unit"
    return {
        "package_record_id": record_id,
        "package_id": package_label,
        "identity": identity,
        "quantity": _decimal_text(remaining),
        "unit": unit,
        "unit_key": unit.casefold(),
        "lab_testing_state": str(row.get("LabTestingState") or row.get("LabTestResultStatus") or "").strip(),
        "delivery_id": str(delivery.get("Id") or delivery.get("DeliveryId") or "").strip(),
    }


def fetch_confirmed_inbound_snapshot(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    transfer_id: int | str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Return a strict, license-scoped snapshot for one pending inbound transfer.

    This helper intentionally performs no write. The transfer must first be
    present in the incoming queue for the exact verified facility license, and
    every delivery package page must load successfully. Any missing expansion
    fails the preflight closed instead of producing a partial receipt snapshot.
    """

    requested_id = str(transfer_id or "").strip()
    if not requested_id:
        return {"ok": False, "status": "missing_transfer", "message": "A Metrc transfer id is required."}

    incoming = fetch_all_incoming_transfers(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        license_number=license_number,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    if not incoming.get("ok"):
        return incoming
    transfer = next((row for row in incoming.get("transfers") or [] if _transfer_id(row) == requested_id), None)
    if transfer is None:
        return {
            "ok": False,
            "status": "transfer_not_pending",
            "message": "The transfer is no longer present in the exact facility inbound queue.",
        }

    deliveries_result = fetch_all_transfer_deliveries(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        transfer_id=requested_id,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    if not deliveries_result.get("ok"):
        return deliveries_result

    packages: list[dict[str, str]] = []
    for delivery in deliveries_result.get("deliveries") or []:
        delivery_id = str(delivery.get("Id") or delivery.get("DeliveryId") or "").strip()
        if not delivery_id:
            return {
                "ok": False,
                "status": "incomplete_transfer",
                "message": "A Metrc delivery has no id, so the inbound snapshot cannot be verified completely.",
            }
        package_result = fetch_all_delivery_packages(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            delivery_id=delivery_id,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
        if not package_result.get("ok"):
            return package_result
        for row in package_result.get("packages") or []:
            canonical = _canonical_inbound_package(row, delivery)
            if canonical is not None:
                packages.append(canonical)

    packages.sort(key=lambda row: (row["identity"].casefold(), row["delivery_id"], row["package_record_id"]))
    return {
        "ok": True,
        "status": "verified_read",
        "message": "The pending inbound transfer was read through the exact verified facility mapping.",
        "transfer_id": requested_id,
        "manifest": str(transfer.get("ManifestNumber") or "").strip(),
        "vendor": str(transfer.get("ShipperFacilityName") or transfer.get("ShipperFacilityLicenseNumber") or "").strip(),
        "vendor_license": str(transfer.get("ShipperFacilityLicenseNumber") or "").strip(),
        "packages": packages,
    }
