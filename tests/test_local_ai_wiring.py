from __future__ import annotations

from backend.app.config import Settings
from backend.app.services import ai_runtime
from services.ai.provider import ProviderUnavailable
from services.ai.providers.local import LocalOpenAIProvider
from services.ai.retrieval.embeddings import LocalEmbeddingProvider
from services.ai.router import ProviderRouter
from services.ai.schemas import AIRequest


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

    def raise_for_status(self):
        if not self.ok:
            raise AssertionError(f"unexpected HTTP {self.status_code}")


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


def test_access_headers_are_sent_for_health_and_chat(monkeypatch):
    captured = []

    def get(url, **kwargs):
        captured.append((url, kwargs))
        return _HTTPResponse({"data": [{"id": "qwen3:14b"}]})

    def post(url, **kwargs):
        captured.append((url, kwargs))
        return _HTTPResponse({"choices": [{"message": {"content": "online"}}]})

    monkeypatch.setattr("services.ai.providers.local.requests.get", get)
    monkeypatch.setattr("services.ai.providers.local.requests.post", post)
    provider = LocalOpenAIProvider(
        base_url="https://ai-runtime.doobielogic.io",
        model="qwen3:14b",
        access_client_id="service-id",
        access_client_secret="service-secret",
    )

    assert provider.health().reachable is True
    provider.generate(AIRequest("request", "system", [{"role": "user", "content": "hello"}]))

    assert [item[0] for item in captured] == [
        "https://ai-runtime.doobielogic.io/v1/models",
        "https://ai-runtime.doobielogic.io/v1/chat/completions",
    ]
    for _url, kwargs in captured:
        assert kwargs["headers"]["CF-Access-Client-Id"] == "service-id"
        assert kwargs["headers"]["CF-Access-Client-Secret"] == "service-secret"


def test_access_headers_are_sent_for_embedding_health_and_generation(monkeypatch):
    captured = []

    def post(url, **kwargs):
        captured.append((url, kwargs))
        return _HTTPResponse({"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    monkeypatch.setattr("services.ai.retrieval.embeddings.requests.post", post)
    provider = LocalEmbeddingProvider(
        base_url="https://ai-runtime.doobielogic.io",
        model="embeddinggemma:latest",
        access_client_id="service-id",
        access_client_secret="service-secret",
    )

    assert provider.health().reachable is True
    assert provider.embed(["inventory"])[0] == [0.1, 0.2]
    assert {item[0] for item in captured} == {"https://ai-runtime.doobielogic.io/v1/embeddings"}
    for _url, kwargs in captured:
        assert kwargs["headers"]["CF-Access-Client-Id"] == "service-id"
        assert kwargs["headers"]["CF-Access-Client-Secret"] == "service-secret"


def test_public_runtime_configuration_never_contains_access_secrets():
    public = ai_runtime._public_runtime_configuration(
        {
            "provider_mode": "local_only",
            "local_llm_base_url": "https://ai-runtime.doobielogic.io",
            "local_llm_access_client_id": "service-id",
            "local_llm_access_client_secret": "service-secret",
            "local_llm_api_key": "api-secret",
        }
    )

    serialized = repr(public)
    assert "service-id" not in serialized
    assert "service-secret" not in serialized
    assert "api-secret" not in serialized


def test_local_only_router_does_not_call_cloud_provider():
    class OfflineLocal:
        name = "local"
        local = True

        def health(self):
            from services.ai.schemas import ProviderHealth
            return ProviderHealth("local", True, False, "qwen3:14b", True, True, True, "ConnectionError")

        def supports_tools(self):
            return True

        def supports_structured_output(self):
            return True

        def generate(self, request):
            raise AssertionError("offline provider must not generate")

    class CloudProvider(OfflineLocal):
        name = "openai"
        local = False

        def health(self):
            raise AssertionError("cloud provider must not be inspected in local-only mode")

    router = ProviderRouter(
        {"local": OfflineLocal(), "openai": CloudProvider()},
        order=["local", "openai"],
        allow_cloud_fallback=False,
    )

    try:
        router.generate(AIRequest("request", "system", [{"role": "user", "content": "hello"}]))
    except ProviderUnavailable as exc:
        assert "local:unavailable:ConnectionError" in str(exc)
    else:
        raise AssertionError("local-only outage must return a bounded unavailable error")
