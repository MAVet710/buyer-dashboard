from __future__ import annotations

import requests

from services.doobie_client import DoobieClient


class _DummyResponse:
    status_code = 200

    @staticmethod
    def json():
        return {
            "answer": "Prioritize low-stock winners.",
            "explanation": "Grounded in the supplied inventory.",
            "recommendations": ["Review reorder quantities."],
            "confidence": "high",
            "sources": [],
            "mode": "buyer",
            "risk_flags": [],
            "inefficiencies": [],
        }


def test_buyer_brief_uses_v4_contract_and_both_auth_headers(monkeypatch):
    captured = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _DummyResponse()

    monkeypatch.setattr(requests, "post", _fake_post)
    client = DoobieClient("https://doobie.example.com/", "service-key")
    result = client.buyer_brief(
        {"prompt": "Use this exact buyer question.", "rows": [{"days_on_hand": 4}]},
        state="MA",
    )

    assert result["mode"] == "buyer"
    assert captured["url"] == "https://doobie.example.com/api/v1/support/buyer_brief"
    assert captured["json"] == {
        "question": "Use this exact buyer question.",
        "state": "MA",
        "data": {"rows": [{"days_on_hand": 4}]},
    }
    assert captured["headers"]["x-api-key"] == "service-key"
    assert captured["headers"]["Authorization"] == "Bearer service-key"


def test_copilot_normalizes_legacy_personas_to_supported_modes(monkeypatch):
    captured = {}

    def _fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return _DummyResponse()

    monkeypatch.setattr(requests, "post", _fake_post)
    client = DoobieClient("https://doobie.example.com", "service-key")
    client.copilot("What changed?", {"x": 1}, persona="buyer_assistant", state="CA")
    assert captured["json"]["mode"] == "buyer"
    assert captured["json"]["persona"] == "buyer"


def test_copilot_uses_server_side_auto_routing_and_forwards_history(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _DummyResponse()

    monkeypatch.setattr("services.doobie_client.requests.post", fake_post)
    client = DoobieClient("https://doobie.example.com", "service-key")
    client.copilot(
        "How should I review room yield?",
        {"room": ["A"]},
        state="CA",
        history=[{"role": "user", "content": "We are reviewing cultivation."}],
    )

    assert captured["json"]["mode"] == "auto"
    assert captured["json"]["persona"] == "auto"
    assert captured["json"]["history"][0]["role"] == "user"
    assert captured["json"]["state"] == "CA"


def test_updated_v4_response_fields_are_preserved(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "answer": "Which state are you operating in?",
                "mode": "compliance",
                "routed_mode": "compliance",
                "routed_by": "Detected from your question",
                "needs_clarification": True,
                "missing_context": ["jurisdiction"],
                "compliance_context": {"code": None},
                "ai": {"provider": "groq", "enabled": True},
            }

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: Response())
    result = DoobieClient("https://doobie.example.com", "service-key").copilot(
        "What label rule applies?", {}, history=[{"role": "user", "content": "Packaging"}]
    )

    assert result["needs_clarification"] is True
    assert result["missing_context"] == ["jurisdiction"]
    assert result["routed_mode"] == "compliance"
    assert result["ai"]["provider"] == "groq"


def test_capability_snapshot_discovers_updated_doobie_api(monkeypatch):
    payloads = {
        "/health": {
            "status": "ok",
            "ai_provider": "groq",
            "ai_enabled": "true",
            "conversation_ready": "true",
            "app_version": "2026.08-grounded-conversations",
        },
        "/api/v1/auth/check": {
            "authenticated": True,
            "service": "DoobieLogic",
            "api_version": "v4",
        },
        "/api/v1/knowledge/modules": {"modules": {"buyer": {}, "packaging": {}}},
        "/api/v1/knowledge/professional-domains": {"domains": {"quality": {}, "security": {}}},
        "/api/v1/compliance/jurisdictions": {"count": 56, "jurisdictions": []},
    }

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        path = url.removeprefix("https://doobie.example.com")
        return Response(payloads[path])

    monkeypatch.setattr(requests, "get", fake_get)
    snapshot = DoobieClient("https://doobie.example.com", "service-key").capability_snapshot()

    assert snapshot["ok"] is True
    assert snapshot["api_version"] == "v4"
    assert snapshot["jurisdiction_count"] == 56
    assert snapshot["modules"] == ["buyer", "packaging"]
    assert snapshot["professional_domains"] == ["quality", "security"]
    assert snapshot["conversation_ready"] is True


def test_client_can_probe_public_no_key_development_deployment(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok"}

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    client = DoobieClient("https://doobie.example.com", "")

    assert client.enabled is True
    assert client.authenticated is False
    assert client.health()["ok"] is True
    assert "Authorization" not in client._headers()
