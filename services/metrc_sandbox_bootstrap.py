"""Metrc Connect sandbox bootstrap for creating/looking up a sandbox user.

This endpoint is different from normal Metrc API authentication: before a
sandbox User API Key exists, Metrc instructs integrators to authenticate the
setup request with the Metrc Connect vendor/integrator key in the x-metrc-key
header. Normal Metrc Basic Auth is used only after the sandbox user key exists.

No credential is logged or returned in request metadata. The caller is
responsible for storing any returned/generated User API Key in encrypted secret
storage rather than source control.
"""

from __future__ import annotations

from typing import Any, Callable

import requests

from services.metrc_client import resolve_metrc_base_url


class MetrcSandboxBootstrapError(RuntimeError):
    """Raised when the sandbox setup call cannot be made safely."""


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        text = str(getattr(response, "text", "")).strip()
        return text[:2000] if text else None


def _extract_user_key(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("UserKey", "userKey", "ApiKey", "apiKey", "Key", "key"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        for key in ("Data", "data", "Result", "result"):
            nested = payload.get(key)
            found = _extract_user_key(nested)
            if found:
                return found
    if isinstance(payload, list):
        for row in payload:
            found = _extract_user_key(row)
            if found:
                return found
    return ""


def setup_ma_sandbox_integrator(
    *,
    vendor_api_key: str,
    user_key: str = "",
    timeout_seconds: int = 30,
    request_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Create or look up the Massachusetts sandbox integrator user.

    - Without ``user_key``: initiates sandbox user creation.
    - With ``user_key``: asks Metrc for the current setup associated with that
      key, following the setup endpoint's optional ``userKey`` query parameter.

    The x-metrc-key credential is never included in the returned evidence.
    """

    vendor_api_key = str(vendor_api_key or "").strip()
    if not vendor_api_key:
        raise MetrcSandboxBootstrapError("A Metrc Connect vendor/integrator API key is required.")

    base_url, state_code = resolve_metrc_base_url("MA", environment="sandbox")
    if state_code != "MA" or not base_url:
        raise MetrcSandboxBootstrapError("The verified Massachusetts sandbox base URL is not configured.")
    if "sandbox-api-ma.metrc.com" not in base_url.casefold():
        raise MetrcSandboxBootstrapError("Integrator setup must target the verified Massachusetts sandbox host.")

    url = f"{base_url.rstrip('/')}/sandbox/v2/integrator/setup"
    query = {"userKey": str(user_key).strip()} if str(user_key or "").strip() else None
    try:
        response = (request_fn or requests.request)(
            "POST",
            url,
            headers={
                "x-metrc-key": vendor_api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params=query,
            json={},
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise MetrcSandboxBootstrapError(
            f"Metrc sandbox integrator setup request failed: {type(exc).__name__}."
        ) from exc

    payload = _response_payload(response)
    http_status = int(getattr(response, "status_code", 0) or 0)
    returned_user_key = _extract_user_key(payload)
    ok = bool(200 <= http_status < 300)
    return {
        "ok": ok,
        "state": state_code,
        "environment": "sandbox",
        "http_status": http_status,
        "request": {
            "method": "POST",
            "path": "sandbox/v2/integrator/setup",
            "query": {"userKey": "[provided]"} if query else {},
            "auth": "x-metrc-key header",
            "body": {},
        },
        "response": payload,
        "user_key": returned_user_key,
        "user_key_returned": bool(returned_user_key),
        "message": (
            "Metrc accepted the sandbox integrator setup request."
            if ok and not returned_user_key
            else "Metrc returned a sandbox User API Key; store it as an encrypted secret."
            if ok
            else f"Metrc rejected sandbox integrator setup with HTTP {http_status}."
        ),
    }
