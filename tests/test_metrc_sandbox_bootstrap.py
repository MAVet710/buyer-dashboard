from __future__ import annotations

import pytest

from services import metrc_sandbox_bootstrap as subject


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}" if payload is not None else b""
        self.text = ""

    def json(self):
        return self._payload


def test_first_time_setup_uses_vendor_header_without_basic_auth(monkeypatch):
    monkeypatch.setattr(
        subject,
        "resolve_metrc_base_url",
        lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"),
    )
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, {"Status": "Pending"})

    result = subject.setup_ma_sandbox_integrator(
        vendor_api_key="vendor-secret",
        request_fn=request,
    )

    assert result["ok"] is True
    assert result["user_key_returned"] is False
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://sandbox-api-ma.metrc.com/sandbox/v2/integrator/setup"
    assert calls[0][2]["headers"]["x-metrc-key"] == "vendor-secret"
    assert "auth" not in calls[0][2]
    assert calls[0][2]["params"] is None
    assert calls[0][2]["json"] == {}
    assert "vendor-secret" not in str(result)


def test_lookup_sends_user_key_only_as_query_and_returns_key(monkeypatch):
    monkeypatch.setattr(
        subject,
        "resolve_metrc_base_url",
        lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"),
    )
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, {"UserKey": "generated-user-key"})

    result = subject.setup_ma_sandbox_integrator(
        vendor_api_key="vendor-secret",
        user_key="lookup-key",
        request_fn=request,
    )

    assert calls[0][2]["params"] == {"userKey": "lookup-key"}
    assert result["user_key"] == "generated-user-key"
    assert result["request"]["query"] == {"userKey": "[provided]"}
    assert "lookup-key" not in str(result["request"])
    assert "vendor-secret" not in str(result)


def test_non_2xx_is_reported_without_claiming_success(monkeypatch):
    monkeypatch.setattr(
        subject,
        "resolve_metrc_base_url",
        lambda state, environment: ("https://sandbox-api-ma.metrc.com", "MA"),
    )
    result = subject.setup_ma_sandbox_integrator(
        vendor_api_key="vendor-secret",
        request_fn=lambda *args, **kwargs: FakeResponse(401, {"Message": "Unauthorized"}),
    )
    assert result["ok"] is False
    assert result["http_status"] == 401
    assert result["user_key"] == ""


def test_setup_refuses_missing_key_or_wrong_host(monkeypatch):
    with pytest.raises(subject.MetrcSandboxBootstrapError, match="vendor/integrator"):
        subject.setup_ma_sandbox_integrator(vendor_api_key="")

    monkeypatch.setattr(
        subject,
        "resolve_metrc_base_url",
        lambda state, environment: ("https://api-ma.metrc.com", "MA"),
    )
    with pytest.raises(subject.MetrcSandboxBootstrapError, match="sandbox host"):
        subject.setup_ma_sandbox_integrator(vendor_api_key="vendor")
