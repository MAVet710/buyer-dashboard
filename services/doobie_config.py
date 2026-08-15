from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st

RUNTIME_CONFIG_PATH = Path(os.environ.get("DOOBIE_RUNTIME_CONFIG_PATH", ".streamlit/doobie_runtime_config.json"))
DOOBIE_SERVICE_API_KEY = "DOOBIE_SERVICE_API_KEY"
DOOBIE_LICENSE_KEY = "DOOBIE_LICENSE_KEY"
DOOBIE_ADMIN_API_KEY = "DOOBIE_ADMIN_API_KEY"
METRC_API_KEY = "METRC_API_KEY"
DEFAULT_DOOBIE_BASE_URL = "https://doobie-api.onrender.com"
DEFAULT_SERVICE_AUTH_TIMEOUT_SECONDS = 75
DEFAULT_TRANSIENT_FAILURE_CACHE_SECONDS = 5
TRANSIENT_CONNECTION_STATUSES = {"timeout", "server_unavailable", "waking_up"}


def _safe_secret(*keys: str) -> str:
    try:
        for key in keys:
            value = st.secrets.get(key)
            if value:
                return str(value).strip()
    except Exception:
        return ""
    return ""


def mask_api_key(api_key: str, visible: int = 4) -> str:
    raw = str(api_key or "")
    if not raw:
        return ""
    if len(raw) <= visible:
        return "*" * len(raw)
    return f"{'*' * (len(raw) - visible)}{raw[-visible:]}"


def get_default_doobie_config() -> dict[str, str]:
    base_url = (
        os.environ.get("DOOBIE_BASE_URL")
        or os.environ.get("DOOBIE_AI_BASE_URL")
        or os.environ.get("DOOBIELOGIC_URL")
        or _safe_secret("DOOBIE_BASE_URL", "DOOBIE_AI_BASE_URL", "DOOBIELOGIC_URL")
        or DEFAULT_DOOBIE_BASE_URL
    ).strip()
    api_key = (
        os.environ.get("DOOBIE_SERVICE_API_KEY")
        or os.environ.get("DOOBIE_API_KEY")
        or os.environ.get("DOOBIELOGIC_API_KEY")
        or _safe_secret("DOOBIE_SERVICE_API_KEY", "DOOBIE_API_KEY", "DOOBIELOGIC_API_KEY")
        or ""
    ).strip()
    return {
        "base_url": base_url,
        "api_key": api_key,
        "source": "env_or_secrets" if (base_url or api_key) else "unavailable",
    }


def get_session_doobie_config() -> dict[str, str | bool | None]:
    return {
        "base_url": str(st.session_state.get("doobie_base_url") or "").strip(),
        "api_key": str(st.session_state.get("doobie_api_key") or "").strip(),
        "connected": bool(st.session_state.get("doobie_connected")),
        "status": str(st.session_state.get("doobie_status") or "").strip() if isinstance(st.session_state.get("doobie_status"), str) else None,
        "source": "session",
    }


def get_global_doobie_config() -> dict[str, str | bool | None]:
    return {
        "base_url": str(st.session_state.get("global_doobie_base_url") or "").strip(),
        "api_key": str(st.session_state.get("global_doobie_api_key") or "").strip(),
        "status": str(st.session_state.get("global_doobie_status") or "").strip(),
        "source": "admin_global",
    }


def _load_local_runtime_config() -> dict[str, str]:
    try:
        if not RUNTIME_CONFIG_PATH.exists():
            return {"base_url": "", "api_key": "", "source": "unavailable"}
        payload = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"base_url": "", "api_key": "", "source": "unavailable"}
        return {
            "base_url": str(payload.get("base_url") or "").strip(),
            "api_key": str(payload.get("api_key") or "").strip(),
            "source": "local_runtime",
        }
    except Exception:
        return {"base_url": "", "api_key": "", "source": "unavailable"}


def resolve_doobie_config() -> dict[str, str | bool]:
    session_cfg = get_session_doobie_config()
    if session_cfg.get("base_url") and session_cfg.get("api_key"):
        return {
            "base_url": str(session_cfg.get("base_url") or ""),
            "api_key": str(session_cfg.get("api_key") or ""),
            "source": "session",
            "connected": bool(session_cfg.get("connected")),
            "available": True,
        }

    global_cfg = get_global_doobie_config()
    if global_cfg.get("base_url") and global_cfg.get("api_key"):
        return {
            "base_url": str(global_cfg.get("base_url") or ""),
            "api_key": str(global_cfg.get("api_key") or ""),
            "source": "admin_global",
            "connected": str(global_cfg.get("status") or "") == "connected",
            "available": True,
        }

    default_cfg = get_default_doobie_config()
    if default_cfg.get("base_url"):
        return {
            "base_url": str(default_cfg.get("base_url") or ""),
            "api_key": str(default_cfg.get("api_key") or ""),
            "source": "env_or_secrets",
            "connected": bool(default_cfg.get("api_key")),
            "available": True,
        }

    local_cfg = _load_local_runtime_config()
    if local_cfg.get("base_url") and local_cfg.get("api_key"):
        return {
            "base_url": str(local_cfg.get("base_url") or ""),
            "api_key": str(local_cfg.get("api_key") or ""),
            "source": "local_runtime",
            "connected": False,
            "available": True,
        }

    return {
        "base_url": "",
        "api_key": "",
        "source": "unavailable",
        "connected": False,
        "available": False,
    }


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
            return {
                "ok": True,
                "status": "connected",
                "message": "Connected to Doobie AI",
                "validated_at": _utc_now_iso(),
                "api_version": str(payload.get("api_version") or ""),
                "authenticated": bool(payload.get("authenticated", True)),
            }
        if auth_resp.status_code in {401, 403}:
            if not key:
                return {
                    "ok": False,
                    "status": "missing_key",
                    "message": "Doobie is reachable but requires a service API key.",
                }
            return {"ok": False, "status": "unauthorized", "message": "Unauthorized: API key was rejected."}
        if auth_resp.status_code >= 500:
            return {"ok": False, "status": "server_unavailable", "message": "Server unavailable. Please retry."}
        if auth_resp.status_code == 404:
            health_resp = requests.get(f"{base}/health", timeout=timeout_seconds)
            if health_resp.status_code < 400:
                return {"ok": True, "status": "connected", "message": "Connected", "validated_at": _utc_now_iso()}
            return {"ok": False, "status": "server_unavailable", "message": "Server unavailable. Please retry."}
        return {
            "ok": False,
            "status": "server_unavailable",
            "message": f"Connection failed with status {auth_resp.status_code}.",
        }
    except requests.Timeout:
        return {"ok": False, "status": "timeout", "message": "Connection timed out."}
    except requests.RequestException:
        return {"ok": False, "status": "server_unavailable", "message": "Server unavailable or unreachable."}


def sync_doobie_service_connection(
    timeout_seconds: int | None = None,
    cache_seconds: int = 300,
    transient_failure_cache_seconds: int = DEFAULT_TRANSIENT_FAILURE_CACHE_SECONDS,
) -> dict[str, str | bool] | None:
    """Authenticate configured app-to-Doobie credentials once per session window.

    Render's free service can need roughly a minute to wake after an idle period.
    Successful and credential failures may be cached normally, but transient
    network/cold-start failures are cached only briefly so the app self-heals.
    """

    config = resolve_doobie_config()
    base_url = str(config.get("base_url") or "").strip().rstrip("/")
    api_key = str(config.get("api_key") or "").strip()
    if config.get("source") == "session":
        connected = bool(st.session_state.get("doobie_connected"))
        return {
            "ok": connected,
            "status": str(st.session_state.get("doobie_status") or ("connected" if connected else "not_connected")),
            "message": "Connected to Doobie AI" if connected else "Doobie is not connected.",
        }
    if not base_url or not api_key:
        return None

    if timeout_seconds is None:
        try:
            timeout_seconds = int(
                os.environ.get(
                    "DOOBIE_SERVICE_AUTH_TIMEOUT_SECONDS",
                    DEFAULT_SERVICE_AUTH_TIMEOUT_SECONDS,
                )
            )
        except (TypeError, ValueError):
            timeout_seconds = DEFAULT_SERVICE_AUTH_TIMEOUT_SECONDS
    timeout_seconds = max(4, int(timeout_seconds))

    fingerprint = hashlib.sha256(f"{base_url}\0{api_key}".encode("utf-8")).hexdigest()
    now_epoch = datetime.now(timezone.utc).timestamp()
    cached = st.session_state.get("_doobie_service_connection_cache")
    cached_result = dict(cached.get("result") or {}) if isinstance(cached, dict) else {}
    cached_status = str(cached_result.get("status") or "").strip().lower()
    cached_ttl = (
        transient_failure_cache_seconds
        if cached_status in TRANSIENT_CONNECTION_STATUSES
        else cache_seconds
    )
    if (
        isinstance(cached, dict)
        and cached.get("fingerprint") == fingerprint
        and now_epoch - float(cached.get("checked_at") or 0) < max(1, int(cached_ttl))
    ):
        result = cached_result
    else:
        result = test_doobie_connection(base_url, api_key, timeout_seconds=timeout_seconds)
        st.session_state["_doobie_service_connection_cache"] = {
            "fingerprint": fingerprint,
            "checked_at": now_epoch,
            "result": dict(result),
        }

    connected = bool(result.get("ok"))
    result_status = str(result.get("status") or "not_connected").strip().lower()
    session_status = "waking_up" if result_status in TRANSIENT_CONNECTION_STATUSES else result_status
    st.session_state.doobie_status = session_status
    st.session_state.doobie_connected = connected
    if connected:
        st.session_state.doobie_base_url = base_url
        st.session_state.doobie_api_key = api_key
        st.session_state.doobie_last_validated = result.get("validated_at")
    return result


def clear_session_doobie_config() -> None:
    for key in [
        "doobie_base_url",
        "doobie_api_key",
        "doobie_connected",
        "doobie_status",
        "doobie_last_validated",
        "doobie_features",
        "_doobie_service_connection_cache",
    ]:
        st.session_state.pop(key, None)
