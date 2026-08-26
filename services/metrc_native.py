"""Deterministic Metrc write adapters for approved traceability actions.

Only explicitly mapped operations are allowed. There is intentionally no generic
"send arbitrary JSON" escape hatch.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import requests

from services.metrc_client import MetrcConfigurationError, resolve_metrc_base_url


class MetrcNativeError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None, retryable: bool = False, response: Any = None):
        super().__init__(message)
        self.http_status = http_status
        self.retryable = retryable
        self.response = response


def _request(
    *, state: str, integrator_api_key: str, user_api_key: str, method: str, path: str, payload: Any, timeout: int = 30
) -> dict[str, Any]:
    if not all(str(value or "").strip() for value in (integrator_api_key, user_api_key)):
        raise MetrcNativeError("Metrc integration credentials are incomplete.")
    try:
        base = resolve_metrc_base_url(state)
    except MetrcConfigurationError as exc:
        raise MetrcNativeError(str(exc)) from exc
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    try:
        response = requests.request(
            method.upper(),
            url,
            auth=(integrator_api_key, user_api_key),
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise MetrcNativeError(f"Metrc request failed: {exc}", retryable=True) from exc
    parsed: Any = None
    if response.content:
        try:
            parsed = response.json()
        except ValueError:
            parsed = {"message": response.text[:1000]}
    if response.status_code == 429:
        raise MetrcNativeError("Metrc rate limited the request.", http_status=429, retryable=True, response=parsed)
    if response.status_code in {401, 403}:
        raise MetrcNativeError("Metrc rejected the saved API keys or license permissions.", http_status=response.status_code, response=parsed)
    if response.status_code >= 500:
        raise MetrcNativeError(f"Metrc returned HTTP {response.status_code}.", http_status=response.status_code, retryable=True, response=parsed)
    if not response.ok:
        raise MetrcNativeError(f"Metrc rejected the operation with HTTP {response.status_code}.", http_status=response.status_code, response=parsed)
    return {"http_status": response.status_code, "payload": parsed, "url_path": path}


def submit_metrc_action(
    *,
    state: str,
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    operation_type: str,
    entity_id: str,
    payload: dict[str, Any],
    reason: str = "",
) -> dict[str, Any]:
    operation = str(operation_type or "").strip().casefold()
    label = str(entity_id or "").strip()
    if not label:
        raise MetrcNativeError("A Metrc package label/entity ID is required.")
    query = f"?licenseNumber={requests.utils.quote(str(license_number).strip(), safe='')}"
    if operation == "package_finish":
        body = [{"Label": label, "ActualDate": str(payload.get("actual_date") or date.today().isoformat())}]
        return _request(state=state, integrator_api_key=integrator_api_key, user_api_key=user_api_key, method="PUT", path=f"packages/v2/finish{query}", payload=body)
    if operation == "package_adjust":
        quantity = payload.get("quantity_delta")
        unit = str(payload.get("unit") or "").strip()
        adjustment_reason = str(payload.get("reason") or reason or "").strip()
        if quantity in (None, "") or not unit or not adjustment_reason:
            raise MetrcNativeError("Metrc package adjustment requires quantity_delta, unit, and reason.")
        body = [{
            "Label": label,
            "Quantity": float(quantity),
            "UnitOfMeasure": unit,
            "AdjustmentReason": adjustment_reason,
            "AdjustmentDate": str(payload.get("adjustment_date") or date.today().isoformat()),
            "ReasonNote": str(payload.get("reason_note") or reason or "")[:500],
        }]
        return _request(state=state, integrator_api_key=integrator_api_key, user_api_key=user_api_key, method="PUT", path=f"packages/v2/adjust{query}", payload=body)
    raise MetrcNativeError(f"Metrc operation '{operation}' is not enabled for automatic dispatch.")
