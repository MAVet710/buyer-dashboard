from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st

RUNTIME_CONFIG_PATH = Path(os.environ.get("DOOBIE_RUNTIME_CONFIG_PATH", ".streamlit/doobie_runtime_config.json"))


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
        or os.environ.get("DOOBIELOGIC_URL")
        or _safe_secret("DOOBIE_BASE_URL", "DOOBIELOGIC_URL")
        or ""
    ).strip()
    api_key = (
        os.environ.get("DOOBIE_API_KEY")
        or os.environ.get("DOOBIELOGIC_API_KEY")
        or _safe_secret("DOOBIE_API_KEY", "DOOBIELOGIC_API_KEY")
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

    local_cfg = _load_local_runtime_config()
    if local_cfg.get("base_url") and local_cfg.get("api_key"):
        return {
            "base_url": str(local_cfg.get("base_url") or ""),
            "api_key": str(local_cfg.get("api_key") or ""),
            "source": "local_runtime",
            "connected": False,
            "available": True,
        }

    default_cfg = get_default_doobie_config()
    if default_cfg.get("base_url") and default_cfg.get("api_key"):
        return {
            "base_url": str(default_cfg.get("base_url") or ""),
            "api_key": str(default_cfg.get("api_key") or ""),
            "source": "env_or_secrets",
            "connected": True,
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
    if not key:
        return {"ok": False, "status": "missing_key", "message": "Doobie API key is required."}

    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "status": "invalid_url", "message": "Invalid URL. Include http:// or https://."}

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        auth_resp = requests.get(f"{base}/api/v1/auth/check", headers=headers, timeout=timeout_seconds)
        if auth_resp.status_code in {200, 204}:
            return {"ok": True, "status": "connected", "message": "Connected", "validated_at": _utc_now_iso()}
        if auth_resp.status_code in {401, 403}:
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


def clear_session_doobie_config() -> None:
    for key in [
        "doobie_base_url",
        "doobie_api_key",
        "doobie_connected",
        "doobie_status",
        "doobie_last_validated",
        "doobie_features",
    ]:
        st.session_state.pop(key, None)
