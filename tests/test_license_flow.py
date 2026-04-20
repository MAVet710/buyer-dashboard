from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from services.license_session import (
    build_cached_license_session,
    is_license_recheck_needed,
    license_in_grace_period,
    license_is_valid_and_fresh,
    load_local_license_session,
    save_local_license_session,
)
from services import license_client


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_no_local_session_requires_key_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("BUYER_DASHBOARD_LICENSE_FILE", str(tmp_path / ".license.json"))
    assert load_local_license_session() is None


def test_valid_key_response_saves_local_session(tmp_path, monkeypatch):
    monkeypatch.setenv("BUYER_DASHBOARD_LICENSE_FILE", str(tmp_path / ".license.json"))
    payload = {
        "valid": True,
        "company_name": "Acme Cannabis",
        "customer_id": "cust_123",
        "plan_type": "premium",
        "status": "active",
        "features": {"buyer_module": True},
    }
    session = build_cached_license_session("lic_abc", payload)
    save_local_license_session(session)

    cached = load_local_license_session()
    assert cached is not None
    assert cached["license_key"] == "lic_abc"
    assert cached["valid"] is True


def test_invalid_key_response_blocks(monkeypatch):
    monkeypatch.setenv("DOOBIE_BASE_URL", "https://licenses.example.com")

    def _fake_post(*args, **kwargs):
        return _DummyResponse(401, {"reason": "invalid_key"})

    monkeypatch.setattr(license_client.requests, "post", _fake_post)
    result = license_client.validate_license_key("bad_key")
    assert result["ok"] is True
    assert result["valid"] is False
    assert result["reason"] == "invalid_key"


def test_validate_request_contract_and_headers(monkeypatch):
    monkeypatch.setenv("DOOBIE_BASE_URL", "https://licenses.example.com/")
    monkeypatch.setenv("DOOBIE_API_KEY", "svc_key")
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _DummyResponse(200, {"valid": True, "status": "active"})

    monkeypatch.setattr(license_client.requests, "post", _fake_post)
    result = license_client.validate_license_key("lic_good")
    assert result["ok"] is True
    assert result["valid"] is True
    assert captured["args"][0] == "https://licenses.example.com/api/v1/license/validate"
    assert captured["kwargs"]["json"] == {"license_key": "lic_good"}
    headers = captured["kwargs"]["headers"]
    assert headers["x-api-key"] == "svc_key"
    assert headers["Authorization"] == "Bearer svc_key"


def test_legacy_env_var_fallbacks(monkeypatch):
    monkeypatch.delenv("DOOBIE_BASE_URL", raising=False)
    monkeypatch.delenv("DOOBIE_API_KEY", raising=False)
    monkeypatch.setenv("DOOBIELOGIC_URL", "https://legacy.example.com")
    monkeypatch.setenv("DOOBIELOGIC_API_KEY", "legacy_key")
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _DummyResponse(200, {"valid": True})

    monkeypatch.setattr(license_client.requests, "post", _fake_post)
    result = license_client.validate_license_key("lic_legacy")
    assert result["ok"] is True
    assert captured["args"][0] == "https://legacy.example.com/api/v1/license/validate"
    headers = captured["kwargs"]["headers"]
    assert headers["x-api-key"] == "legacy_key"
    assert headers["Authorization"] == "Bearer legacy_key"


def test_default_doobie_base_url_fallback(monkeypatch):
    monkeypatch.delenv("DOOBIE_BASE_URL", raising=False)
    monkeypatch.delenv("DOOBIELOGIC_URL", raising=False)
    captured = {}

    def _fake_post(*args, **kwargs):
        captured["args"] = args
        return _DummyResponse(200, {"valid": True})

    monkeypatch.setattr(license_client.requests, "post", _fake_post)
    result = license_client.validate_license_key("lic_default")
    assert result["ok"] is True
    assert captured["args"][0] == "https://doobie-api.onrender.com/api/v1/license/validate"


def test_stale_key_triggers_recheck():
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    assert is_license_recheck_needed(stale_ts, recheck_hours=24) is True


def test_recent_valid_session_loads_app():
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    session = {
        "valid": True,
        "status": "active",
        "validated_at": recent_ts,
    }
    assert license_is_valid_and_fresh(session, recheck_hours=24) is True


def test_doobie_unavailable_no_valid_cache_blocked(monkeypatch):
    monkeypatch.setenv("DOOBIE_BASE_URL", "https://licenses.example.com")

    def _raise_error(*args, **kwargs):
        raise requests.RequestException("down")

    monkeypatch.setattr(license_client.requests, "post", _raise_error)
    result = license_client.validate_license_key("candidate")
    assert result["ok"] is False
    assert result["reason"] == "license_request_error"


def test_unauthorized_maps_reason(monkeypatch):
    monkeypatch.setenv("DOOBIE_BASE_URL", "https://licenses.example.com")

    def _fake_post(*args, **kwargs):
        return _DummyResponse(401, {})

    monkeypatch.setattr(license_client.requests, "post", _fake_post)
    result = license_client.validate_license_key("candidate")
    assert result["ok"] is True
    assert result["valid"] is False
    assert result["reason"] == "unauthorized"


def test_doobie_unavailable_recent_valid_cache_grace_allowed():
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
    session = {
        "valid": True,
        "status": "active",
        "validated_at": recent_ts,
    }
    assert license_in_grace_period(session, grace_hours=48) is True
