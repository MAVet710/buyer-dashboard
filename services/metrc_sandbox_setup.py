from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests

from modules.regulatory.registry import resolve_metrc_base_url


class MetrcSandboxSetupError(RuntimeError):
    """Raised when sandbox user provisioning cannot be attempted safely."""


def _redact_provider_payload(value: Any) -> Any:
    """Return provider diagnostics without ever echoing a credential-like field."""

    if isinstance(value, list):
        return [_redact_provider_payload(row) for row in value]
    if not isinstance(value, dict):
        return value
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        normalized = "".join(ch for ch in str(key).casefold() if ch.isalnum())
        if normalized in {"userkey", "userapikey", "apikey", "integratorkey", "integratorapikey"}:
            redacted[str(key)] = "***"
        else:
            redacted[str(key)] = _redact_provider_payload(item)
    return redacted


def provision_metrc_sandbox_user(
    *,
    state: str,
    integrator_api_key: str,
    timeout_seconds: int = 12,
    request_post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Request a Metrc sandbox user using the Metrc Connect integrator key.

    This is the special sandbox bootstrap call, not a normal Basic-Auth Metrc
    request. It intentionally uses only the x-metrc-key header and never accepts
    an arbitrary URL. The state must resolve to a registry-verified sandbox host.
    """

    base_url, state_code = resolve_metrc_base_url(state, environment="sandbox")
    if not base_url:
        raise MetrcSandboxSetupError("Select a jurisdiction with a verified Metrc sandbox deployment.")
    key = str(integrator_api_key or "").strip()
    if not key:
        raise MetrcSandboxSetupError("Save the Metrc Integrator / Vendor API Key before provisioning a sandbox user.")

    url = f"{base_url}/sandbox/v2/integrator/setup"
    try:
        response = (request_post or requests.post)(
            url,
            headers={
                "x-metrc-key": key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={},
            timeout=timeout_seconds,
        )
    except requests.Timeout as exc:
        raise MetrcSandboxSetupError("Metrc sandbox user provisioning timed out.") from exc
    except requests.RequestException as exc:
        raise MetrcSandboxSetupError(f"Metrc sandbox provisioning request failed: {type(exc).__name__}.") from exc

    status_code = int(response.status_code)
    try:
        payload: Any = response.json()
    except ValueError:
        payload = {"message": str(getattr(response, "text", "") or "")[:500]}
    safe_payload = _redact_provider_payload(payload)

    result: dict[str, Any] = {
        "ok": status_code == 200,
        "http_status": status_code,
        "state": state_code,
        "environment": "sandbox",
        "base_url": base_url,
        "endpoint": "/sandbox/v2/integrator/setup",
        "provider_response": safe_payload,
    }
    if status_code == 200:
        return result | {
            "status": "requested",
            "message": (
                "Metrc accepted the sandbox integrator setup request. "
                "The sandbox User API Key is sent to the integrator contact email on file."
            ),
        }
    if status_code == 400:
        return result | {"status": "validation_error", "message": "Metrc rejected the sandbox setup request as invalid."}
    if status_code == 401:
        return result | {"status": "auth_failed", "message": "Metrc rejected the saved Integrator / Vendor API Key."}
    if status_code == 403:
        return result | {"status": "sandbox_forbidden", "message": "Metrc refused the sandbox-only setup endpoint for this target."}
    if status_code == 429:
        return result | {
            "status": "rate_limited",
            "message": "Metrc rate limited the sandbox setup request.",
            "retry_after": str(response.headers.get("Retry-After", "")),
        }
    return result | {"status": "provider_error", "message": f"Metrc returned HTTP {status_code} during sandbox setup."}
