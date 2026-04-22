from __future__ import annotations

import requests

from services.doobie_client import DoobieClient


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_support_health_check_success(monkeypatch):
    client = DoobieClient(base_url="https://doobie.example.com", api_key="key")

    def _fake_post(*args, **kwargs):
        return _DummyResponse(200, {"answer": "AI health check OK.", "mode": "live"})

    monkeypatch.setattr(requests, "post", _fake_post)
    result = client.support_copilot_health_check()
    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["health_phrase_present"] is True


def test_support_health_check_endpoint_missing(monkeypatch):
    client = DoobieClient(base_url="https://doobie.example.com", api_key="key")

    def _fake_post(*args, **kwargs):
        return _DummyResponse(404, {"detail": "not found"})

    monkeypatch.setattr(requests, "post", _fake_post)
    result = client.support_copilot_health_check()
    assert result["ok"] is False
    assert result["error_code"] == "endpoint_missing"


def test_support_health_check_fallback_detected(monkeypatch):
    client = DoobieClient(base_url="https://doobie.example.com", api_key="key")

    def _fake_post(*args, **kwargs):
        return _DummyResponse(200, {"answer": "Doobie is currently unavailable.", "mode": "fallback"})

    monkeypatch.setattr(requests, "post", _fake_post)
    result = client.support_copilot_health_check()
    assert result["ok"] is False
    assert result["error_code"] == "fallback_response_detected"
