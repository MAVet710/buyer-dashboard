from __future__ import annotations

from backend.app.config import Settings
from services.ai.providers.local import LocalOpenAIProvider


class _HTTPResponse:
    ok = True
    status_code = 200

    def json(self):
        return {"data": [{"id": "qwen3:14b"}]}


def test_hosted_local_llm_default_allows_workstation_inference_latency():
    settings = Settings(_env_file=None)
    assert settings.local_llm_timeout_seconds == 120.0


def test_health_probe_uses_bounded_tunnel_friendly_timeout(monkeypatch):
    captured: dict[str, float] = {}

    def get(url, **kwargs):
        captured["timeout"] = float(kwargs["timeout"])
        return _HTTPResponse()

    monkeypatch.setattr("services.ai.providers.local.requests.get", get)
    provider = LocalOpenAIProvider(
        base_url="https://ai-runtime.doobielogic.io",
        model="qwen3:14b",
        timeout_seconds=120,
    )

    health = provider.health()

    assert health.reachable is True
    assert captured["timeout"] == 20.0


def test_health_probe_never_exceeds_shorter_configured_timeout(monkeypatch):
    captured: dict[str, float] = {}

    def get(url, **kwargs):
        captured["timeout"] = float(kwargs["timeout"])
        return _HTTPResponse()

    monkeypatch.setattr("services.ai.providers.local.requests.get", get)
    provider = LocalOpenAIProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:14b",
        timeout_seconds=4,
    )

    health = provider.health()

    assert health.reachable is True
    assert captured["timeout"] == 4.0


def test_generation_uses_full_configured_timeout(monkeypatch):
    captured: dict[str, float] = {}

    def post(url, **kwargs):
        captured["timeout"] = float(kwargs["timeout"])
        return type(
            "Response",
            (),
            {
                "status_code": 200,
                "json": lambda self: {
                    "choices": [{"message": {"content": "online"}, "finish_reason": "stop"}],
                    "usage": {},
                },
            },
        )()

    monkeypatch.setattr("services.ai.providers.local.requests.post", post)
    provider = LocalOpenAIProvider(
        base_url="https://ai-runtime.doobielogic.io",
        model="qwen3:14b",
        timeout_seconds=120,
    )

    from services.ai.schemas import AIRequest

    response = provider.generate(
        AIRequest(
            request_id="timeout-test",
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
        )
    )

    assert response.text == "online"
    assert captured["timeout"] == 120.0
