from __future__ import annotations

import os
from typing import Any

import requests


LICENSE_VALIDATE_PATH = "/api/v1/license/validate"
DEFAULT_TIMEOUT_SECONDS = 8


def _base_url() -> str:
    primary = str(os.getenv("DOOBIE_BASE_URL", "")).strip()
    if primary:
        return primary.rstrip("/")
    legacy = str(os.getenv("DOOBIELOGIC_URL", "")).strip()
    return legacy.rstrip("/")


def _api_key() -> str:
    primary = str(os.getenv("DOOBIE_API_KEY", "")).strip()
    if primary:
        return primary
    return str(os.getenv("DOOBIELOGIC_API_KEY", "")).strip()


def validate_license_key(license_key: str) -> dict[str, Any]:
    """
    Validate a Buyer Dashboard license key with DoobieLogic.

    Returns:
      {
        "ok": bool,                # request completed (HTTP 2xx and JSON parsed)
        "valid": bool,             # DoobieLogic license validity
        "reason": str | None,      # validation error or server-side reason
        "payload": dict,           # raw parsed JSON payload from DoobieLogic (if available)
        "status_code": int | None,
      }
    """
    key = str(license_key or "").strip()
    if not key:
        return {
            "ok": False,
            "valid": False,
            "reason": "missing_license_key",
            "payload": {},
            "status_code": None,
        }

    base_url = _base_url()
    if not base_url:
        return {
            "ok": False,
            "valid": False,
            "reason": "missing_doobie_base_url",
            "payload": {},
            "status_code": None,
        }

    headers = {"Content-Type": "application/json"}
    api_key = _api_key()
    if api_key:
        headers["x-api-key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"

    timeout_seconds = int(os.getenv("DOOBIE_LICENSE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))

    try:
        response = requests.post(
            f"{base_url}{LICENSE_VALIDATE_PATH}",
            json={"license_key": key},
            headers=headers,
            timeout=timeout_seconds,
        )
        status_code = int(response.status_code)

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if status_code >= 500:
            return {
                "ok": False,
                "valid": False,
                "reason": "license_server_error",
                "payload": payload if isinstance(payload, dict) else {},
                "status_code": status_code,
            }

        if status_code >= 400:
            reason = None
            if isinstance(payload, dict):
                reason = payload.get("reason") or payload.get("error") or payload.get("message")
            if status_code in {401, 403}:
                default_reason = "unauthorized"
            elif status_code == 404:
                default_reason = "license_endpoint_not_found"
            elif status_code == 408:
                default_reason = "license_timeout"
            else:
                default_reason = "license_invalid"
            return {
                "ok": True,
                "valid": False,
                "reason": str(reason or default_reason),
                "payload": payload if isinstance(payload, dict) else {},
                "status_code": status_code,
            }

        if not isinstance(payload, dict):
            payload = {}

        is_valid = bool(payload.get("valid", False))
        reason = payload.get("reason") or payload.get("message")
        return {
            "ok": True,
            "valid": is_valid,
            "reason": str(reason) if reason else None,
            "payload": payload,
            "status_code": status_code,
        }

    except requests.Timeout:
        return {
            "ok": False,
            "valid": False,
            "reason": "license_timeout",
            "payload": {},
            "status_code": None,
        }
    except requests.RequestException:
        return {
            "ok": False,
            "valid": False,
            "reason": "license_request_error",
            "payload": {},
            "status_code": None,
        }
