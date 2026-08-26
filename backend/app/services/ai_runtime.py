from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import Engine, text

from modules.integrations import IntegrationConfigurationService
from services.ai import AgentRuntime
from services.ai.context import system_prompt
from services.ai.provider import ProviderUnavailable
from services.ai.retrieval import KnowledgeRetriever, KnowledgeScope, KnowledgeStore, LocalEmbeddingProvider
from services.ai.router import ProviderRouter
from services.ai.schemas import AIRequest
from services.ai.telemetry import AITelemetry
from services.ai.validation import parse_structured
from services.ai.providers import GeminiProvider, LocalOpenAIProvider, OpenAIProvider

from ..auth import RequestContext
from ..config import Settings
from .ai_datasets import build_dataset_registry, facility_access


_NATIVE_PROVIDERS = {"local", "gemini", "openai"}


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


def _public_runtime_configuration(config: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "provider_mode", "provider_order", "allow_cloud_fallback", "local_llm_base_url", "local_llm_model",
        "local_embedding_base_url", "local_embedding_model", "status", "secret_hint",
    }
    return {key: config.get(key) for key in allowed if key in config}


def _native_provider_order(config: dict[str, Any], settings: Settings) -> tuple[list[str], str, bool]:
    """Resolve saved routing while permanently excluding the retired Doobie bridge."""
    mode = str(config.get("provider_mode") or settings.ai_provider_mode or "local_only").strip().casefold()
    raw_order = str(config.get("provider_order") or settings.ai_provider_order or "local")
    requested = [value.strip().casefold() for value in raw_order.split(",") if value.strip()]
    order = [value for value in requested if value in _NATIVE_PROVIDERS]
    if mode == "local_only":
        order = ["local"]
    elif not order:
        # Old installations may still have provider_order=doobie. Native AI must
        # recover to local instead of reviving the retired platform integration.
        order = ["local"]
    allow_fallback = bool(config.get("allow_cloud_fallback", settings.ai_allow_cloud_fallback)) and mode != "local_only"
    return order, mode, allow_fallback


def build_runtime(*, engine: Engine, settings: Settings, context: RequestContext, operation_type: str) -> tuple[AgentRuntime, Any, str, str, dict[str, Any]]:
    config = runtime_configuration(engine, settings)
    local = LocalOpenAIProvider(
        base_url=str(config.get("local_llm_base_url") or ""),
        model=str(config.get("local_llm_model") or ""),
        api_key=str(config.get("local_llm_api_key") or ""),
        access_client_id=settings.local_llm_access_client_id,
        access_client_secret=settings.local_llm_access_client_secret,
        timeout_seconds=settings.local_llm_timeout_seconds,
        max_tokens=settings.local_llm_max_tokens,
        temperature=settings.local_llm_temperature,
    )
    providers: dict[str, Any] = {"local": local}
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if settings.openai_api_key and settings.openai_model:
        providers["openai"] = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.local_llm_timeout_seconds,
        )

    order, mode, allow_fallback = _native_provider_order(config, settings)
    router = ProviderRouter(providers, order=order, allow_cloud_fallback=allow_fallback)

    # Surface the effective, sanitized routing. The retired `doobie` provider is
    # deliberately absent even if a stale saved configuration still names it.
    config["provider_mode"] = mode
    config["provider_order"] = ",".join(order)
    config["allow_cloud_fallback"] = allow_fallback

    embedding_base = str(config.get("local_embedding_base_url") or config.get("local_llm_base_url") or "")
    embedding_model = str(config.get("local_embedding_model") or "")
    embeddings = LocalEmbeddingProvider(
        base_url=embedding_base,
        model=embedding_model,
        api_key=str(settings.local_embedding_api_key or config.get("local_llm_api_key") or ""),
        access_client_id=settings.local_llm_access_client_id,
        access_client_secret=settings.local_llm_access_client_secret,
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
        **_public_runtime_configuration(config),
        "providers": router.health(),
        "embedding": embeddings.health().__dict__ if embeddings else {"configured": False, "reachable": False, "model": "", "detail": "lexical fallback active"},
        "knowledge": store.health(KnowledgeScope(context.organization_id, context.facility_id)),
        "dataset_registry": list(registry.keys()),
    }


def run_bounded_ai(
    *,
    engine: Engine,
    settings: Settings,
    context: RequestContext,
    operation_type: str,
    profile: Any,
    question: str,
    bounded_context: dict[str, Any],
) -> dict[str, Any]:
    """Run server-authorized bounded context through the DoobieLogic-owned AI runtime.

    This is for application workflows that already computed the exact data slice
    they want interpreted. It deliberately does not call the legacy Doobie API.
    """
    runtime, _access, organization_name, facility_name, _status = build_runtime(
        engine=engine,
        settings=settings,
        context=context,
        operation_type=operation_type,
    )

    prompt = system_prompt(
        profile,
        organization_name=organization_name,
        facility_name=facility_name,
        operation_type=operation_type,
        tool_names=(),
        dataset_keys=(),
        knowledge_required=False,
    )
    prompt += (
        "\nThe server has supplied a bounded, authorized data context for this request. "
        "Use that context for factual claims. Do not invent values that are not present. "
        "Do not claim that a tool was executed. "
        "Answer the user's question directly and concisely. "
        "Prioritize the most important findings rather than listing every row. "
        "Do not create a markdown table unless the user explicitly asks for one."
    )

    request_id = uuid.uuid4().hex
    serialized = json.dumps(bounded_context, default=str)[:6000]
    request = AIRequest(
        request_id=request_id,
        system_prompt=prompt,
        messages=[
            {"role": "user", "content": str(question or "").strip()},
            {
                "role": "user",
                "content": "Server-authorized bounded context: " + serialized,
            },
        ],
        max_tokens=settings.local_llm_max_tokens,
        metadata={
            "agent_key": profile.key,
            "bounded_context": True,
        },
    )

    try:
        decision = runtime.provider_router.generate(
            request,
            validate=lambda response: (
                (True, "direct_answer")
                if str(response.text or "").strip()
                else (False, "empty_response")
            ),
        )
    except ProviderUnavailable as exc:
        return {
            "answer": "DoobieLogic AI is currently unavailable.",
            "summary": "AI provider unavailable",
            "recommendations": [],
            "warnings": [str(exc)],
            "missing_data": [],
            "confidence": 0.0,
            "grounding": "data",
            "provider": "unavailable",
            "model": "",
            "local": True,
            "fallback_used": False,
            "fallback_reason": "",
            "mode": "fallback",
            "request_id": request_id,
        }

    response = decision.response
    parsed = parse_structured(response) or {"answer": response.text}
    return {
        "answer": str(parsed.get("answer") or response.text or "").strip(),
        "summary": str(parsed.get("summary") or ""),
        "priority": str(parsed.get("priority") or "normal"),
        "recommendations": [str(value) for value in parsed.get("recommendations") or []][:20],
        "warnings": [str(value) for value in parsed.get("warnings") or []][:20],
        "missing_data": [str(value) for value in parsed.get("missing_data") or []][:20],
        "confidence": float(parsed.get("confidence") or 0.0),
        "grounding": "data",
        "provider": response.provider,
        "model": response.model,
        "local": response.local,
        "fallback_used": decision.fallback_used,
        "fallback_reason": decision.fallback_reason,
        "mode": "local_ai" if response.local else "ai",
        "request_id": request_id,
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
