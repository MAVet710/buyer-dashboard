from __future__ import annotations

import requests

from services.metrc_client import MetrcTransport, resolve_metrc_base_url, test_metrc_connection as run_metrc_connection_test


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
    assert resolve_metrc_base_url("https://api-mi.metrc.com/") == ("https://api-mi.metrc.com", "MI")


def test_resolver_rejects_unverified_arbitrary_metrc_url():
    assert resolve_metrc_base_url("https://api-zz.metrc.com") == ("", "HTTPS://API-ZZ.METRC.COM")


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


def test_transport_retries_transient_failure_and_preserves_correlation_without_secrets():
    calls = []
    responses = iter((_DummyResponse(503, {"message": "temporary"}), _DummyResponse(200, [{"Id": 1}], {"X-RateLimit-Remaining": "19"})))

    def request_get(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    result = MetrcTransport(
        state="OR", integrator_api_key="integrator-secret", user_api_key="user-secret",
        request_get=request_get, sleeper=lambda _seconds: None,
    ).get("facilities/v2/", correlation_id="corr-123")

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert result["correlation_id"] == "corr-123"
    assert result["rate_limit_remaining"] == "19"
    assert calls[0][1]["auth"] == ("integrator-secret", "user-secret")
    assert calls[0][1]["headers"]["X-Correlation-ID"] == "corr-123"
    assert "integrator-secret" not in repr(result)
    assert "user-secret" not in repr(result)


def test_transport_sanitizes_non_json_provider_error():
    response = _DummyResponse(500, None)
    result = MetrcTransport(
        state="OR", integrator_api_key="integrator-secret", user_api_key="user-secret",
        max_attempts=1, request_get=lambda *args, **kwargs: response,
    ).get("packages/v2/active")
    assert result["status"] == "provider_error"
    assert result["message"] == "Metrc returned HTTP 500."
    assert "integrator-secret" not in repr(result)
