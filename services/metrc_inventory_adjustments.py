from __future__ import annotations

from datetime import date
from typing import Any

import requests

from services.metrc_client import resolve_metrc_base_url


def _request(
    method: str,
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_payload: Any = None,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    base_url, state_code = resolve_metrc_base_url(state)
    if not base_url:
        return {"ok": False, "status": "missing_state", "message": "Enter a valid Metrc state or API base URL."}
    if not str(integrator_api_key or "").strip():
        return {"ok": False, "status": "missing_integrator_key", "message": "METRC_INTEGRATOR_API_KEY is not configured."}
    if not str(user_api_key or "").strip():
        return {"ok": False, "status": "missing_user_key", "message": "A Metrc user API key is required."}

    try:
        response = requests.request(
            method.upper(),
            f"{base_url}/{str(path).lstrip('/')}",
            auth=(str(integrator_api_key).strip(), str(user_api_key).strip()),
            params=params or {},
            json=json_payload,
            timeout=timeout_seconds,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except requests.Timeout:
        return {"ok": False, "status": "timeout", "message": "Metrc did not respond before the timeout.", "state": state_code}
    except requests.RequestException as exc:
        return {"ok": False, "status": "request_error", "message": f"Metrc request failed: {type(exc).__name__}.", "state": state_code}

    result: dict[str, Any] = {
        "ok": 200 <= response.status_code < 300,
        "http_status": int(response.status_code),
        "state": state_code,
    }
    if response.status_code == 401:
        result.update(status="auth_failed", message="Metrc rejected the integrator/user API key pair.")
        return result
    if response.status_code == 403:
        result.update(status="forbidden", message="Metrc authenticated the keys, but this user does not have permission to adjust package inventory.")
        return result
    if response.status_code == 429:
        result.update(status="rate_limited", message="Metrc rate limited the request.", retry_after=response.headers.get("Retry-After", ""))
        return result
    if response.status_code >= 400:
        message = f"Metrc returned HTTP {response.status_code}."
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(payload.get("Message") or payload.get("message") or message)
        except ValueError:
            pass
        result.update(status="http_error", message=message)
        return result

    payload: Any = None
    if response.content:
        try:
            payload = response.json()
        except ValueError:
            payload = None
    result.update(status="connected", message="Metrc request succeeded.", payload=payload)
    return result


def fetch_package_adjustment_reasons(
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

    rows: list[dict[str, Any]] = []
    page = 1
    while page <= 50:
        result = _request(
            "GET",
            state=state,
            user_api_key=user_api_key,
            integrator_api_key=integrator_api_key,
            path="packages/v2/adjust/reasons",
            params={"licenseNumber": license_number, "pageNumber": page, "pageSize": 20},
            timeout_seconds=timeout_seconds,
        )
        if not result.get("ok"):
            return result
        payload = result.get("payload")
        data = payload.get("Data") if isinstance(payload, dict) else payload
        if isinstance(data, list):
            rows.extend(dict(item) for item in data if isinstance(item, dict))
        total_pages = int(payload.get("TotalPages") or 1) if isinstance(payload, dict) else 1
        if page >= total_pages:
            break
        page += 1
    return {"ok": True, "status": "connected", "message": "Adjustment reasons loaded.", "reasons": rows}


def normalize_metrc_unit(value: str) -> str:
    token = str(value or "").strip().casefold()
    aliases = {
        "g": "Grams",
        "gram": "Grams",
        "grams": "Grams",
        "kg": "Kilograms",
        "kilogram": "Kilograms",
        "kilograms": "Kilograms",
        "oz": "Ounces",
        "ounce": "Ounces",
        "ounces": "Ounces",
        "lb": "Pounds",
        "pound": "Pounds",
        "pounds": "Pounds",
        "unit": "Each",
        "units": "Each",
        "each": "Each",
        "ea": "Each",
        "count": "Each",
    }
    return aliases.get(token, str(value or "").strip())


def submit_package_adjustment(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    package_label: str,
    adjustment_type: str,
    quantity: float,
    unit: str,
    reason: str,
    reason_note: str = "",
    adjustment_date: date | None = None,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    license_number = str(license_number or "").strip()
    package_label = str(package_label or "").strip()
    reason = str(reason or "").strip()
    if not license_number:
        return {"ok": False, "status": "missing_license", "message": "A Metrc facility license is required."}
    if not package_label:
        return {"ok": False, "status": "missing_package", "message": "An External Package ID is required for Metrc sync."}
    if not reason:
        return {"ok": False, "status": "missing_reason", "message": "An adjustment reason is required."}

    mode = str(adjustment_type or "incremental").strip().casefold().replace(" ", "_")
    method = "PUT" if mode in {"absolute", "set_quantity", "set"} else "POST"
    payload = [
        {
            "Label": package_label,
            "Quantity": float(quantity),
            "UnitOfMeasure": normalize_metrc_unit(unit),
            "AdjustmentReason": reason,
            "AdjustmentDate": (adjustment_date or date.today()).isoformat(),
            "ReasonNote": str(reason_note or "").strip() or None,
        }
    ]
    result = _request(
        method,
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path="packages/v2/adjust",
        params={"licenseNumber": license_number},
        json_payload=payload,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["message"] = "Metrc package adjustment succeeded."
    return result
