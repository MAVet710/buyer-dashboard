from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

import requests

from modules.regulatory.registry import resolve_metrc_base_url


@dataclass(frozen=True)
class MetrcTransport:
    """Reusable read transport with bounded retries and sanitized evidence."""

    state: str
    integrator_api_key: str
    user_api_key: str
    timeout_seconds: int = 12
    max_attempts: int = 3
    request_get: Callable[..., Any] | None = None
    sleeper: Callable[[float], None] = time.sleep

    def get(self, path: str, params: dict[str, Any] | None = None, *, correlation_id: str = "") -> dict[str, Any]:
        base_url, state_code = resolve_metrc_base_url(self.state)
        correlation_id = str(correlation_id or uuid.uuid4())
        if not base_url:
            return self._error("missing_state", "Select a verified Metrc jurisdiction.", correlation_id, state_code, base_url)
        if not str(self.integrator_api_key or "").strip():
            return self._error("missing_integrator_key", "METRC_INTEGRATOR_API_KEY is not configured.", correlation_id, state_code, base_url)
        if not str(self.user_api_key or "").strip():
            return self._error("missing_user_key", "A Metrc user API key is required.", correlation_id, state_code, base_url)
        attempts = max(1, min(int(self.max_attempts), 5))
        url = f"{base_url}/{str(path).lstrip('/')}"
        for attempt in range(1, attempts + 1):
            try:
                response = (self.request_get or requests.get)(
                    url,
                    auth=(self.integrator_api_key, self.user_api_key),
                    params=params or {},
                    timeout=self.timeout_seconds,
                    headers={"Accept": "application/json", "X-Correlation-ID": correlation_id},
                )
            except requests.Timeout:
                if attempt < attempts:
                    self.sleeper(min(0.1 * (2 ** (attempt - 1)), 0.5))
                    continue
                return self._error("timeout", "Metrc did not respond before the timeout.", correlation_id, state_code, base_url, attempts=attempt)
            except requests.RequestException as exc:
                if attempt < attempts:
                    self.sleeper(min(0.1 * (2 ** (attempt - 1)), 0.5))
                    continue
                return self._error("request_error", f"Metrc request failed: {type(exc).__name__}.", correlation_id, state_code, base_url, attempts=attempt)

            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < attempts:
                retry_after = _bounded_retry_after(response.headers.get("Retry-After"))
                self.sleeper(retry_after if retry_after is not None else min(0.1 * (2 ** (attempt - 1)), 0.5))
                continue
            result = self._response(response, correlation_id, state_code, base_url, attempt)
            return result
        return self._error("request_error", "Metrc request failed.", correlation_id, state_code, base_url, attempts=attempts)

    @staticmethod
    def _error(status: str, message: str, correlation_id: str, state: str, base_url: str, *, attempts: int = 0) -> dict[str, Any]:
        return {"ok": False, "status": status, "message": message, "correlation_id": correlation_id,
                "state": state, "base_url": base_url, "attempts": attempts}

    @staticmethod
    def _response(response: Any, correlation_id: str, state: str, base_url: str, attempts: int) -> dict[str, Any]:
        status_code = int(response.status_code)
        result: dict[str, Any] = {"ok": status_code == 200, "http_status": status_code, "state": state,
                                  "base_url": base_url, "correlation_id": correlation_id, "attempts": attempts,
                                  "rate_limit_remaining": response.headers.get("X-RateLimit-Remaining", "")}
        if status_code == 401:
            return result | {"status": "auth_failed", "message": "Metrc rejected the saved API keys."}
        if status_code == 403:
            return result | {"status": "forbidden", "message": "The Metrc user lacks permission for this resource."}
        if status_code == 429:
            return result | {"status": "rate_limited", "message": "Metrc rate limited the request.", "retry_after": response.headers.get("Retry-After", "")}
        if status_code >= 400:
            return result | {"status": "provider_error", "message": f"Metrc returned HTTP {status_code}."}
        try:
            payload = response.json()
        except ValueError:
            return result | {"ok": False, "status": "invalid_json", "message": "Metrc returned an invalid JSON response."}
        return result | {"status": "connected", "message": "Metrc request succeeded.", "payload": payload}


def _bounded_retry_after(value: Any) -> float | None:
    try:
        return max(0.0, min(float(value), 0.5))
    except (TypeError, ValueError):
        return None


def get_default_metrc_integrator_key() -> dict[str, str]:
    key = str(
        os.environ.get("METRC_INTEGRATOR_API_KEY")
        or os.environ.get("METRC_SOFTWARE_API_KEY")
        or ""
    ).strip()
    return {
        "api_key": key,
        "source": "env" if key else "unavailable",
    }


def _extract_facility_license(facility: Any) -> str:
    if not isinstance(facility, dict):
        return ""
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        if facility.get(key):
            return str(facility.get(key) or "").strip()
    license_payload = facility.get("License") or facility.get("license")
    if isinstance(license_payload, dict):
        for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            if license_payload.get(key):
                return str(license_payload.get(key) or "").strip()
    return ""


def _facility_label(facility: Any) -> str:
    if not isinstance(facility, dict):
        return ""
    label = (
        facility.get("Name")
        or facility.get("DisplayName")
        or facility.get("Alias")
        or facility.get("name")
        or facility.get("displayName")
        or ""
    )
    license_number = _extract_facility_license(facility)
    if label and license_number:
        return f"{label} ({license_number})"
    return str(label or license_number or "").strip()


def _metrc_get(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    path: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = 12,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Perform one authenticated, read-only Metrc v2 request."""
    return MetrcTransport(
        state=state,
        user_api_key=str(user_api_key or "").strip(),
        integrator_api_key=str(integrator_api_key or "").strip(),
        timeout_seconds=timeout_seconds,
    ).get(path, params, correlation_id=correlation_id)


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("Data")
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
    return []


def fetch_metrc_incoming_transfers(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Fetch the facility's current incoming transfer queue without mutating Metrc."""

    license_number = str(license_number or "").strip()
    if not license_number:
        return {"ok": False, "status": "missing_license", "message": "A Metrc facility license is required."}
    result = _metrc_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path="transfers/v2/incoming",
        params={"licenseNumber": license_number, "pageSize": 20, "pageNumber": 1},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["transfers"] = _payload_rows(result.get("payload"))
    return result


def fetch_metrc_transfer_deliveries(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    transfer_id: int | str,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Fetch deliveries associated with one inbound transfer."""

    result = _metrc_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path=f"transfers/v2/{transfer_id}/deliveries",
        params={"pageSize": 20, "pageNumber": 1},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["deliveries"] = _payload_rows(result.get("payload"))
    return result


def fetch_metrc_delivery_packages(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    delivery_id: int | str,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Fetch package details for one inbound transfer delivery."""

    result = _metrc_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        path=f"transfers/v2/deliveries/{delivery_id}/packages",
        params={"pageSize": 20, "pageNumber": 1},
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        result["packages"] = _payload_rows(result.get("payload"))
    return result


def test_metrc_connection(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str = "",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    base_url, state_code = resolve_metrc_base_url(state)
    user_api_key = str(user_api_key or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    license_number = str(license_number or "").strip()

    if not base_url:
        return {
            "ok": False,
            "status": "missing_state",
            "message": "Enter a valid Metrc state code, state name, or API base URL.",
        }
    if not integrator_api_key:
        return {
            "ok": False,
            "status": "missing_integrator_key",
            "message": "METRC_INTEGRATOR_API_KEY is missing from environment or Streamlit secrets.",
            "base_url": base_url,
            "state": state_code,
        }
    if not user_api_key:
        return {
            "ok": False,
            "status": "missing_user_key",
            "message": "Enter the Metrc user API key before testing.",
            "base_url": base_url,
            "state": state_code,
        }

    try:
        resp = requests.get(
            f"{base_url}/facilities/v2/",
            auth=(integrator_api_key, user_api_key),
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )
    except requests.Timeout:
        return {
            "ok": False,
            "status": "timeout",
            "message": "Metrc did not respond before the timeout.",
            "base_url": base_url,
            "state": state_code,
        }
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status": "request_error",
            "message": f"Metrc request failed: {type(exc).__name__}.",
            "base_url": base_url,
            "state": state_code,
        }

    result: dict[str, Any] = {
        "ok": resp.status_code == 200,
        "http_status": int(resp.status_code),
        "base_url": base_url,
        "state": state_code,
    }
    if resp.status_code == 401:
        result.update(
            status="auth_failed",
            message="Metrc rejected the integrator/user API key pair.",
        )
        return result
    if resp.status_code == 403:
        result.update(
            status="forbidden",
            message="Metrc authenticated the keys, but this user is not authorized for the facilities endpoint.",
        )
        return result
    if resp.status_code == 429:
        result.update(
            status="rate_limited",
            message="Metrc rate limited the request.",
            retry_after=resp.headers.get("Retry-After", ""),
        )
        return result
    if resp.status_code >= 400:
        result.update(
            status="http_error",
            message=f"Metrc returned HTTP {resp.status_code}.",
        )
        return result

    try:
        payload = resp.json()
    except ValueError:
        result.update(
            ok=False,
            status="invalid_json",
            message="Metrc responded successfully, but the response was not valid JSON.",
        )
        return result

    facilities = payload if isinstance(payload, list) else []
    facility_labels = [_facility_label(f) for f in facilities]
    facility_labels = [label for label in facility_labels if label]
    result.update(
        status="connected",
        message="Metrc connection succeeded.",
        facility_count=len(facilities),
        facilities_preview=facility_labels[:5],
    )
    if license_number:
        normalized_target = "".join(ch for ch in license_number.upper() if ch.isalnum())
        license_found = any(
            "".join(ch for ch in _extract_facility_license(f).upper() if ch.isalnum()) == normalized_target
            for f in facilities
        )
        result["license_found"] = license_found
        if not license_found:
            result["status"] = "connected_license_not_found"
            result["message"] = "Metrc connected, but the entered facility license was not found in this user's facilities."
    return result
