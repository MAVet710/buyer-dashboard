from services.doobie_client import DoobieClient


class _State(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


def test_doobie_client_uses_license_context_in_payload(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"answer": "ok", "mode": "live"}

    def _fake_post(url, json, headers, timeout):
        captured["json"] = json
        return _Resp()

    import requests
    monkeypatch.setattr(requests, "post", _fake_post)
    client = DoobieClient(base_url="https://x.example.com", api_key="svc")
    client.call_endpoint("/api/v1/support/copilot", {"data": {"x": 1}}, license_context={"license_key": "lic_1", "plan_type": "pro"})
    assert captured["json"]["license_key"] == "lic_1"
    assert captured["json"]["plan_type"] == "pro"


def test_doobie_client_returns_service_key_error_when_unauthorized(monkeypatch):
    class _Resp:
        status_code = 401

        def json(self):
            return {}

    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: _Resp())
    client = DoobieClient(base_url="https://x.example.com", api_key="svc")
    result = client.call_endpoint("/api/v1/support/copilot", {"data": {}})
    assert "service key" in result["answer"].lower()


def test_configured_service_credentials_authenticate_and_populate_session(monkeypatch):
    from types import SimpleNamespace
    import services.doobie_config as config

    session_state = _State()
    monkeypatch.setattr(config, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(
        config,
        "resolve_doobie_config",
        lambda: {
            "base_url": "https://doobie.example.com",
            "api_key": "service-secret",
            "source": "env_or_secrets",
        },
    )
    monkeypatch.setattr(
        config,
        "test_doobie_connection",
        lambda *args, **kwargs: {
            "ok": True,
            "status": "connected",
            "validated_at": "2026-08-15T00:00:00+00:00",
        },
    )

    result = config.sync_doobie_service_connection()

    assert result["ok"] is True
    assert session_state["doobie_connected"] is True
    assert session_state["doobie_status"] == "connected"
    assert session_state["doobie_base_url"] == "https://doobie.example.com"
    assert session_state["doobie_api_key"] == "service-secret"


def test_service_authentication_result_is_cached(monkeypatch):
    from types import SimpleNamespace
    import services.doobie_config as config

    session_state = _State()
    calls = []
    monkeypatch.setattr(config, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(
        config,
        "resolve_doobie_config",
        lambda: {
            "base_url": "https://doobie.example.com",
            "api_key": "service-secret",
            "source": "env_or_secrets",
        },
    )

    def _check(*args, **kwargs):
        calls.append(1)
        return {"ok": False, "status": "unauthorized"}

    monkeypatch.setattr(config, "test_doobie_connection", _check)
    config.sync_doobie_service_connection()
    config.sync_doobie_service_connection()

    assert len(calls) == 1
    assert session_state["doobie_connected"] is False
