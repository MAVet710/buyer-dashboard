from __future__ import annotations

from typing import Any

import requests

LICENSE_VALIDATE_PATH = "/api/v1/license/validate"
DEFAULT_TIMEOUT_SECONDS = 8


def validate_license_key(
    license_key: str,
    *,
    base_url: str,
    api_key: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Validate a Buyer Dash/Doobie trial key without importing Streamlit state."""

    key = str(license_key or "").strip()
    base = str(base_url or "").strip().rstrip("/")
    service_key = str(api_key or "").strip()
    if not key:
        return {"ok": False, "valid": False, "reason": "missing_license_key", "payload": {}, "status_code": None}
    if not base:
        return {"ok": False, "valid": False, "reason": "missing_doobie_base_url", "payload": {}, "status_code": None}

    headers = {"Content-Type": "application/json"}
    if service_key:
        headers.update({"x-api-key": service_key, "Authorization": f"Bearer {service_key}"})

    try:
        response = requests.post(
            f"{base}{LICENSE_VALIDATE_PATH}",
            json={"license_key": key},
            headers=headers,
            timeout=max(1, int(timeout_seconds)),
        )
        status_code = int(response.status_code)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        if status_code >= 500:
            return {"ok": False, "valid": False, "reason": "license_server_error", "payload": payload, "status_code": status_code}
        if status_code >= 400:
            reason = payload.get("reason") or payload.get("error") or payload.get("message")
            default_reason = (
                "unauthorized" if status_code in {401, 403}
                else "license_endpoint_not_found" if status_code == 404
                else "license_timeout" if status_code == 408
                else "license_invalid"
            )
            return {"ok": True, "valid": False, "reason": str(reason or default_reason), "payload": payload, "status_code": status_code}

        return {
            "ok": True,
            "valid": bool(payload.get("valid", False)),
            "reason": str(payload.get("reason") or payload.get("message") or "") or None,
            "payload": payload,
            "status_code": status_code,
        }
    except requests.Timeout:
        return {"ok": False, "valid": False, "reason": "license_timeout", "payload": {}, "status_code": None}
    except requests.RequestException:
        return {"ok": False, "valid": False, "reason": "license_request_error", "payload": {}, "status_code": None}
