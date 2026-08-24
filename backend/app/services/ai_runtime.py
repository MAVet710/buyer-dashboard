from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from modules.integrations import IntegrationConfigurationService
from services.ai import AgentRuntime
from services.ai.retrieval import KnowledgeRetriever, KnowledgeScope, KnowledgeStore, LocalEmbeddingProvider
from services.ai.router import ProviderRouter
from services.ai.telemetry import AITelemetry
from services.ai.providers import DoobieProvider, GeminiProvider, LocalOpenAIProvider, OpenAIProvider
from services.doobie_connection import DEFAULT_DOOBIE_BASE_URL

from ..auth import RequestContext
from ..config import Settings
from .ai_datasets import build_dataset_registry, facility_access


def _integration_service(engine: Engine, settings: Settings) -> IntegrationConfigurationService | None:
    try:
        return IntegrationConfigurationService(engine, settings.integration_encryption_key)
    except RuntimeError:
        return None


def runtime_configuration(engine: Engine, settings: Settings) -> dict[str, Any]:
    config: dict[str, Any] = {
        "provider_mode": settings.ai_provider_mode,
        "provider_order": settings.ai_provider_order,
        "allow_cloud_fallback": settings.ai_allow_cloud_fallback,
        "local_llm_base_url": settings.local_llm_base_url,
        "local_llm_model": settings.local_llm_model,
        "local_embedding_base_url": settings.local_embedding_base_url,
        "local_embedding_model": settings.local_embedding_model,
    }
    service = _integration_service(engine, settings)
    row = service.get("platform", "global", "ai_runtime") if service else None
    if row and service:
        public = service.public(row)
        saved = public.get("configuration") or {}
        for key in config:
            if key in saved and saved[key] not in (None, ""):
                config[key] = saved[key]
        try:
            config["local_llm_api_key"] = service.secret(row)
        except RuntimeError:
            config["local_llm_api_key"] = settings.local_llm_api_key
        config["status"] = public.get("status") or "configured"
        config["secret_hint"] = public.get("secret_hint") or ""
    else:
        config["local_llm_api_key"] = settings.local_llm_api_key
        config["status"] = "configured" if config["local_llm_base_url"] and config["local_llm_model"] else "not_connected"
        config["secret_hint"] = ""
    return config


def _doobie(engine: Engine, settings: Settings) -> tuple[str, str]:
    service = _integration_service(engine, settings)
    row = service.get("platform", "global", "doobie") if service else None
    if not row or not service:
        return DEFAULT_DOOBIE_BASE_URL, ""
    public = service.public(row)
    configuration = public.get("configuration") or {}
    try:
        secret = service.secret(row)
    except RuntimeError:
        secret = ""
    return str(configuration.get("base_url") or DEFAULT_DOOBIE_BASE_URL).strip().rstrip("/"), secret


def build_runtime(*, engine: Engine, settings: Settings, context: RequestContext, operation_type: str) -> tuple[AgentRuntime, Any, str, str, dict[str, Any]]:
    config = runtime_configuration(engine, settings)
    local = LocalOpenAIProvider(
        base_url=str(config.get("local_llm_base_url") or ""),
        model=str(config.get("local_llm_model") or ""),
        api_key=str(config.get("local_llm_api_key") or ""),
        timeout_seconds=settings.local_llm_timeout_seconds,
        max_tokens=settings.local_llm_max_tokens,
        temperature=settings.local_llm_temperature,
    )
    providers: dict[str, Any] = {"local": local}
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if settings.openai_api_key and settings.openai_model:
        providers["openai"] = OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model, base_url=settings.openai_base_url, timeout_seconds=settings.local_llm_timeout_seconds)
    doobie_base, doobie_key = _doobie(engine, settings)
    if doobie_key:
        providers["doobie"] = DoobieProvider(base_url=doobie_base, api_key=doobie_key, model=settings.doobie_ai_model)
    order = [value.strip().casefold() for value in str(config.get("provider_order") or settings.ai_provider_order).split(",") if value.strip()]
    mode = str(config.get("provider_mode") or settings.ai_provider_mode).casefold()
    allow_fallback = bool(config.get("allow_cloud_fallback", settings.ai_allow_cloud_fallback)) and mode != "local_only"
    if mode == "local_only":
        order = ["local"]
    router = ProviderRouter(providers, order=order or settings.provider_order, allow_cloud_fallback=allow_fallback)

    embedding_base = str(config.get("local_embedding_base_url") or config.get("local_llm_base_url") or "")
    embedding_model = str(config.get("local_embedding_model") or "")
    embeddings = LocalEmbeddingProvider(
        base_url=embedding_base,
        model=embedding_model,
        api_key=str(settings.local_embedding_api_key or config.get("local_llm_api_key") or ""),
        timeout_seconds=settings.local_embedding_timeout_seconds,
    ) if embedding_base and embedding_model else None
    store = KnowledgeStore(engine)
    retriever = KnowledgeRetriever(store, embeddings)
    registry = build_dataset_registry(context, engine, operation_type=operation_type)
    access, organization_name, facility_name = facility_access(context, engine, operation_type=operation_type)
    runtime = AgentRuntime(
        provider_router=router,
        dataset_registry=registry,
        retriever=retriever,
        telemetry=AITelemetry(engine),
        cloud_cost_rates={
            "gemini": (settings.ai_gemini_input_cost_per_million, settings.ai_gemini_output_cost_per_million),
            "openai": (settings.ai_openai_input_cost_per_million, settings.ai_openai_output_cost_per_million),
        },
    )
    return runtime, access, organization_name, facility_name, {
        **config,
        "providers": router.health(),
        "embedding": embeddings.health().__dict__ if embeddings else {"configured": False, "reachable": False, "model": "", "detail": "lexical fallback active"},
        "knowledge": store.health(KnowledgeScope(context.organization_id, context.facility_id)),
        "dataset_registry": list(registry.keys()),
    }


def diagnostics(*, engine: Engine, settings: Settings, context: RequestContext, operation_type: str = "retail") -> dict[str, Any]:
    runtime, _access, _org, _facility, status = build_runtime(engine=engine, settings=settings, context=context, operation_type=operation_type)
    status["cloud_fallback_enabled"] = runtime.provider_router.allow_cloud_fallback
    status["provider_order"] = list(runtime.provider_router.order)
    try:
        with engine.connect() as connection:
            last_local = connection.execute(text("SELECT timestamp FROM ai_telemetry WHERE is_local AND success ORDER BY timestamp DESC LIMIT 1")).scalar_one_or_none()
            last_fallback = connection.execute(text("SELECT timestamp FROM ai_telemetry WHERE fallback_used ORDER BY timestamp DESC LIMIT 1")).scalar_one_or_none()
        status["last_successful_local_call"] = last_local
        status["last_fallback"] = last_fallback
    except Exception:
        status["last_successful_local_call"] = None
        status["last_fallback"] = None
    return status
