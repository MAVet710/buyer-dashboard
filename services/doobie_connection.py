"""UI-independent Doobie service connection checks."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


DEFAULT_DOOBIE_BASE_URL = "https://doobie-api.onrender.com"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def test_doobie_connection(base_url: str, api_key: str, timeout_seconds: int = 4) -> dict[str, str | bool]:
    base = str(base_url or "").strip().rstrip("/")
    key = str(api_key or "").strip()
    if not base:
        return {"ok": False, "status": "invalid_url", "message": "Doobie base URL is required."}
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "status": "invalid_url", "message": "Invalid URL. Include http:// or https://."}

    headers = {"Content-Type": "application/json"}
    if key:
        headers.update({"Authorization": f"Bearer {key}", "x-api-key": key})
    try:
        auth_resp = requests.get(f"{base}/api/v1/auth/check", headers=headers, timeout=timeout_seconds)
        if auth_resp.status_code in {200, 204}:
            try:
                payload = auth_resp.json()
            except (ValueError, AttributeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            return {"ok": True, "status": "connected", "message": "Connected to Doobie AI", "validated_at": _utc_now_iso(), "api_version": str(payload.get("api_version") or ""), "authenticated": bool(payload.get("authenticated", True))}
        if auth_resp.status_code in {401, 403}:
            if not key:
                return {"ok": False, "status": "missing_key", "message": "Doobie is reachable but requires a service API key."}
            return {"ok": False, "status": "unauthorized", "message": "Unauthorized: API key was rejected."}
        if auth_resp.status_code >= 500:
            return {"ok": False, "status": "server_unavailable", "message": "Server unavailable. Please retry."}
        if auth_resp.status_code == 404:
            health_resp = requests.get(f"{base}/health", timeout=timeout_seconds)
            if health_resp.status_code < 400:
                return {"ok": True, "status": "connected", "message": "Connected", "validated_at": _utc_now_iso()}
            return {"ok": False, "status": "server_unavailable", "message": "Server unavailable. Please retry."}
        return {"ok": False, "status": "server_unavailable", "message": f"Connection failed with status {auth_resp.status_code}."}
    except requests.Timeout:
        return {"ok": False, "status": "timeout", "message": "Connection timed out."}
    except requests.RequestException:
        return {"ok": False, "status": "server_unavailable", "message": "Server unavailable or unreachable."}
