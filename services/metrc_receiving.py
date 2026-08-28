"""Read-only Metrc helpers used by Inventory receiving.

All functions in this module use GET endpoints only. DoobieLogic never accepts a
state transfer, edits a package, or releases lab results from the receiving UI.
Every page is planned through the verified regulatory capability layer before a
network request is made.
"""

from __future__ import annotations

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
