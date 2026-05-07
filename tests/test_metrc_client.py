from __future__ import annotations

import requests

from services.metrc_client import resolve_metrc_base_url, test_metrc_connection as run_metrc_connection_test


class _DummyResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = [] if payload is None else payload
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_resolve_metrc_base_url_state_code():
    assert resolve_metrc_base_url("MA") == ("https://api-ma.metrc.com", "MA")
    assert resolve_metrc_base_url("California") == ("https://api-ca.metrc.com", "CA")
    assert resolve_metrc_base_url("https://api-mi.metrc.com/") == ("https://api-mi.metrc.com", "https://api-mi.metrc.com/")


def test_metrc_connection_success_with_license_match(monkeypatch):
    captured = {}

    def _fake_get(url, auth=None, timeout=None, headers=None):
        captured["url"] = url
        captured["auth"] = auth
        captured["headers"] = headers
        return _DummyResponse(
            200,
            [
                {
                    "Name": "Test Facility",
                    "License": {"Number": "LIC-123"},
                }
            ],
        )

    monkeypatch.setattr(requests, "get", _fake_get)
    result = run_metrc_connection_test(
        state="MA",
        integrator_api_key="integrator-key",
        user_api_key="user-key",
        license_number="LIC-123",
    )

    assert result["ok"] is True
    assert result["status"] == "connected"
    assert result["license_found"] is True
    assert result["facility_count"] == 1
    assert captured["url"] == "https://api-ma.metrc.com/facilities/v2/"
    assert captured["auth"] == ("integrator-key", "user-key")


def test_metrc_connection_reports_missing_integrator_key():
    result = run_metrc_connection_test(
        state="MA",
        integrator_api_key="",
        user_api_key="user-key",
    )

    assert result["ok"] is False
    assert result["status"] == "missing_integrator_key"


def test_metrc_connection_auth_failure(monkeypatch):
    def _fake_get(*args, **kwargs):
        return _DummyResponse(401, {"message": "unauthorized"})

    monkeypatch.setattr(requests, "get", _fake_get)
    result = run_metrc_connection_test(
        state="MA",
        integrator_api_key="integrator-key",
        user_api_key="bad-user-key",
    )

    assert result["ok"] is False
    assert result["status"] == "auth_failed"
    assert result["http_status"] == 401


def test_metrc_connection_rate_limit_includes_retry_after(monkeypatch):
    def _fake_get(*args, **kwargs):
        return _DummyResponse(429, headers={"Retry-After": "30"})

    monkeypatch.setattr(requests, "get", _fake_get)
    result = run_metrc_connection_test(
        state="MA",
        integrator_api_key="integrator-key",
        user_api_key="user-key",
    )

    assert result["ok"] is False
    assert result["status"] == "rate_limited"
    assert result["retry_after"] == "30"
