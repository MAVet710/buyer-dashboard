"""Read-only Metrc helpers used by Inventory receiving.

All functions in this module use GET endpoints only. Buyer Dash never accepts a
state transfer, edits a package, or releases lab results from the receiving UI.
"""

from __future__ import annotations

from typing import Any

from services.metrc_client import _metrc_get, _payload_rows


PAGE_SIZE = 20
MAX_PAGES = 100


def _paged_get(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    path: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Read every available v2 page while preserving Metrc's 20-row page cap."""

    base_params = dict(params or {})
    rows: list[dict[str, Any]] = []
    first_result: dict[str, Any] | None = None
    page = 1
    total_pages = 1
    while page <= min(total_pages, MAX_PAGES):
        request_params = {**base_params, "pageSize": PAGE_SIZE, "pageNumber": page}
        result = _metrc_get(
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            path=path,
            params=request_params,
            timeout_seconds=timeout_seconds,
        )
        if first_result is None:
            first_result = dict(result)
        if not result.get("ok"):
            return result
        payload = result.get("payload")
        rows.extend(_payload_rows(payload))
        if isinstance(payload, dict):
            try:
                total_pages = max(1, int(payload.get("TotalPages") or 1))
            except (TypeError, ValueError):
                total_pages = 1
        else:
            total_pages = 1
        page += 1

    output = first_result or {"ok": True, "status": "connected", "message": "Metrc request succeeded."}
    output["rows"] = rows
    output["page_count"] = min(total_pages, MAX_PAGES)
    output["truncated"] = total_pages > MAX_PAGES
    return output


def fetch_all_incoming_transfers(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    license_number = str(license_number or "").strip()
    if not license_number:
        return {"ok": False, "status": "missing_license", "message": "A Metrc facility license is required."}
    result = _paged_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path="transfers/v2/incoming",
        params={"licenseNumber": license_number},
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
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    result = _paged_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path=f"transfers/v2/{transfer_id}/deliveries",
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
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    result = _paged_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path=f"transfers/v2/deliveries/{delivery_id}/packages",
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
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Retrieve lab test results for one package without changing Metrc."""

    license_number = str(license_number or "").strip()
    package_id = str(package_id or "").strip()
    if not license_number:
        return {"ok": False, "status": "missing_license", "message": "A Metrc facility license is required."}
    if not package_id:
        return {"ok": False, "status": "missing_package", "message": "A Metrc package id is required."}
    result = _paged_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path="labtests/v2/results",
        params={"packageId": package_id, "licenseNumber": license_number},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["lab_results"] = list(result.get("rows") or [])
    return result
