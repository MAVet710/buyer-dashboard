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
    assert captured["json"]["state"] == "CA"
