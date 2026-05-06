from services.doobie_client import DoobieClient


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
