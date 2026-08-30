from __future__ import annotations

from backend.app.config import Settings
from backend.app.services import ai_runtime
from services.ai.providers.local import LocalOpenAIProvider


class _SavedRuntimeService:
    def get(self, scope_type, scope_id, integration_key):
        assert (scope_type, scope_id, integration_key) == ("platform", "global", "ai_runtime")
        return object()

    def public(self, row):
        return {
            "configuration": {
                "provider_mode": "local_first",
                "provider_order": "local,gemini",
                "allow_cloud_fallback": True,
                "local_llm_base_url": "https://saved-inference.example",
                "local_llm_model": "saved-model",
                "local_embedding_base_url": "https://saved-embedding.example",
                "local_embedding_model": "saved-embedding",
            },
            "status": "configured",
            "secret_hint": "saved",
        }

    def secret(self, row):
        return "saved-secret"


class _HTTPResponse:
    def __init__(self, body, *, status_code=200):
        self._body = body
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._body


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_explicit_process_environment_overrides_saved_ai_runtime(monkeypatch):
    monkeypatch.setattr(ai_runtime, "_integration_service", lambda engine, settings: _SavedRuntimeService())
    monkeypatch.setenv("AI_PROVIDER_MODE", "local_only")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "local")
    monkeypatch.setenv("AI_ALLOW_CLOUD_FALLBACK", "false")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "llama3.1")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "local-secret")
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "embeddinggemma")

    settings = _settings()
    config = ai_runtime.runtime_configuration(object(), settings)
    order, mode, allow_fallback = ai_runtime._native_provider_order(config, settings)

    assert config["local_llm_base_url"] == "http://127.0.0.1:11434"
    assert config["local_llm_model"] == "llama3.1"
    assert config["local_llm_api_key"] == "local-secret"
    assert config["local_embedding_base_url"] == "http://127.0.0.1:11434"
    assert config["local_embedding_model"] == "embeddinggemma"
    assert mode == "local_only"
    assert order == ["local"]
    assert allow_fallback is False


def test_saved_ai_runtime_remains_available_without_process_override(monkeypatch):
    monkeypatch.setattr(ai_runtime, "_integration_service", lambda engine, settings: _SavedRuntimeService())
    for name in (
        "AI_PROVIDER_MODE",
        "AI_PROVIDER_ORDER",
        "AI_ALLOW_CLOUD_FALLBACK",
        "LOCAL_LLM_BASE_URL",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_API_KEY",
        "LOCAL_EMBEDDING_BASE_URL",
        "LOCAL_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    config = ai_runtime.runtime_configuration(object(), _settings())

    assert config["local_llm_base_url"] == "https://saved-inference.example"
    assert config["local_llm_model"] == "saved-model"
    assert config["local_llm_api_key"] == "saved-secret"
    assert config["provider_mode"] == "local_first"


def test_local_provider_accepts_ollama_latest_model_alias(monkeypatch):
    monkeypatch.setattr(
        "services.ai.providers.local.requests.get",
        lambda *args, **kwargs: _HTTPResponse({"data": [{"id": "llama3.1:latest"}, {"id": "embeddinggemma:latest"}]}),
    )
    provider = LocalOpenAIProvider(base_url="http://127.0.0.1:11434", model="llama3.1")

    health = provider.health()

    assert health.configured is True
    assert health.reachable is True
    assert health.detail == "ok"


def test_local_provider_reports_missing_configured_model(monkeypatch):
    monkeypatch.setattr(
        "services.ai.providers.local.requests.get",
        lambda *args, **kwargs: _HTTPResponse({"data": [{"id": "qwen3:8b"}, {"id": "embeddinggemma:latest"}]}),
    )
    provider = LocalOpenAIProvider(base_url="http://127.0.0.1:11434", model="llama3.1")

    health = provider.health()

    assert health.configured is True
    assert health.reachable is False
    assert "configured model not found" in health.detail
    assert "qwen3:8b" in health.detail
