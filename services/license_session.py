from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_RECHECK_HOURS = int(os.getenv("DOOBIE_LICENSE_RECHECK_HOURS", "24"))
DEFAULT_GRACE_HOURS = int(os.getenv("DOOBIE_LICENSE_GRACE_HOURS", "48"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _license_cache_path() -> Path:
    configured_path = str(os.getenv("BUYER_DASHBOARD_LICENSE_FILE", ".buyer_dashboard_license.json")).strip()
    return Path(configured_path)


def _to_iso8601(dt: datetime | None = None) -> str:
    value = dt or _utc_now()
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_local_license_session() -> dict[str, Any] | None:
    path = _license_cache_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def save_local_license_session(data: dict[str, Any]) -> None:
    path = _license_cache_path()
    payload = dict(data or {})
    payload["validated_at"] = payload.get("validated_at") or _to_iso8601()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clear_local_license_session() -> None:
    path = _license_cache_path()
    if path.exists():
        path.unlink()


def is_license_recheck_needed(validated_at: str | None, recheck_hours: int = DEFAULT_RECHECK_HOURS) -> bool:
    dt = _parse_iso8601(validated_at)
    if dt is None:
        return True
    return _utc_now() >= (dt + timedelta(hours=max(1, recheck_hours)))


def license_is_valid_and_fresh(session_data: dict[str, Any] | None, recheck_hours: int = DEFAULT_RECHECK_HOURS) -> bool:
    if not isinstance(session_data, dict):
        return False
    if not bool(session_data.get("valid")):
        return False
    if str(session_data.get("status", "")).lower() not in {"active", "trial", "ok", ""}:
        return False
    return not is_license_recheck_needed(str(session_data.get("validated_at") or ""), recheck_hours=recheck_hours)


def license_in_grace_period(session_data: dict[str, Any] | None, grace_hours: int = DEFAULT_GRACE_HOURS) -> bool:
    if not isinstance(session_data, dict):
        return False
    if not bool(session_data.get("valid")):
        return False
    dt = _parse_iso8601(str(session_data.get("validated_at") or ""))
    if dt is None:
        return False
    return _utc_now() <= (dt + timedelta(hours=max(1, grace_hours)))


def get_license_features(session_data: dict[str, Any] | None) -> dict[str, bool]:
    if not isinstance(session_data, dict):
        return {}
    features = session_data.get("features")
    if not isinstance(features, dict):
        return {}
    return {str(k): bool(v) for k, v in features.items()}


def build_cached_license_session(license_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    validated_at = payload.get("validated_at") or _to_iso8601()
    return {
        "license_key": str(license_key),
        "valid": bool(payload.get("valid", False)),
        "company_name": payload.get("company_name") or payload.get("company") or "",
        "customer_id": payload.get("customer_id") or payload.get("account_id") or "",
        "plan_type": payload.get("plan_type") or payload.get("plan") or "",
        "status": payload.get("status") or ("active" if payload.get("valid") else "inactive"),
        "features": features,
        "validated_at": str(validated_at),
        "expires_at": payload.get("expires_at"),
    }
