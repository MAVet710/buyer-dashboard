from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.agent_registry import AgentProfile, PROFILES, resolve_agent_profile
from services.ai.feedback import AgentFeedbackStore
from services.ai.retrieval import KnowledgeIngestionService, KnowledgeScope, KnowledgeStore, LocalEmbeddingProvider
from services.ai.retrieval.ingestion import SUPPORTED_EXTENSIONS
from services.ai.telemetry import AITelemetry

from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.ai_runtime import build_runtime, diagnostics, runtime_configuration

router = APIRouter(prefix="/ai-agents", tags=["ai-agents"])
KNOWLEDGE_ROLES = {"dev", "admin", "supervisor", "qa"}
DIAGNOSTIC_ROLES = {"dev", "admin"}
SOURCE_AUTHORITY = {
    "government": 1,
    "regulation": 1,
    "regulatory_guidance": 1,
    "facility_sop": 2,
    "approved_equipment_sop": 2,
    "internal_policy": 2,
    "manufacturer": 3,
    "metrc": 3,
    "dutchie": 3,
    "technical_reference": 4,
    "peer_reviewed": 4,
    "industry": 5,
    "field_practice": 6,
    "community": 6,
    "internal_document": 6,
}


class AgentMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class AgentRun(BaseModel):
    agent_key: str = Field(default="", max_length=64)
    app_mode: str = Field(default="", max_length=120)
    section: str = Field(default="", max_length=160)
    question: str = Field(min_length=1, max_length=8000)
    history: list[AgentMessage] = Field(default_factory=list, max_length=20)


class FeedbackRequest(BaseModel):
    agent_key: str = Field(default="ops", max_length=64)
    task_type: str = Field(default="user_feedback", max_length=120)
    prompt: str = Field(default="", max_length=8000)
    answer: str = Field(default="", max_length=16000)
    tool_names: list[str] = Field(default_factory=list, max_length=50)
    tool_outcomes: dict[str, Any] = Field(default_factory=dict)
    rating: int | None = Field(default=None, ge=1, le=5)
    corrected_answer: str = Field(default="", max_length=16000)
    provider: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=160)


def _profile_payload(profile: AgentProfile) -> dict[str, Any]:
    return {
        "key": profile.key,
        "name": profile.name,
        "role": profile.role,
        "description": profile.description,
        "focus": list(profile.focus),
        "suggested_questions": list(profile.suggested_questions),
        "compliance_grounded_only": profile.compliance_grounded_only,
    }


def _active_profile(agent_key: str, app_mode: str, section: str) -> AgentProfile:
    requested = str(agent_key or "").strip().casefold()
    if requested:
        profile = PROFILES.get(requested)
        if profile is None:
            raise HTTPException(422, f"Unknown AI agent '{agent_key}'.")
        return profile
    return resolve_agent_profile(app_mode, section)


def _operation_type(app_mode: str, profile: AgentProfile) -> str:
    mode = str(app_mode or "").casefold()
    if "production" in mode or profile.key in {"coman", "extraction", "repack", "cultivation"}:
        return "production"
    return "retail"


def _provider_payload(status: dict[str, Any]) -> dict[str, Any]:
    providers = status.get("providers") if isinstance(status.get("providers"), dict) else {}
    order = status.get("provider_order")
    if isinstance(order, str):
        order = [value.strip().casefold() for value in order.split(",") if value.strip()]
    if not isinstance(order, list):
        order = list(providers)
    reachable = []
    for name in order:
        health = providers.get(name)
        if isinstance(health, dict) and health.get("configured") and health.get("reachable"):
            reachable.append((name, health))
    if reachable:
        name, health = reachable[0]
        display = {"local": "Local AI", "gemini": "Gemini", "openai": "OpenAI", "doobie": "Doobie"}.get(name, name.title())
        return {
            "provider": display,
            "model": health.get("model") or "",
            "configured": True,
            "status": "connected",
            "local": bool(health.get("local")),
            "fallback_configured": len(reachable) > 1,
            "cloud_fallback_enabled": bool(status.get("cloud_fallback_enabled", status.get("allow_cloud_fallback", True))),
        }
    return {
        "provider": "Deterministic analytics",
        "model": "Python / SQL",
        "configured": True,
        "status": "deterministic_only",
        "local": True,
        "fallback_configured": False,
        "cloud_fallback_enabled": bool(status.get("allow_cloud_fallback", True)),
        "message": "Deterministic read-only analytics remain available. Model reasoning is currently offline or not configured.",
    }


def _embedding_provider(engine: Engine, settings: Settings) -> LocalEmbeddingProvider | None:
    config = runtime_configuration(engine, settings)
    base_url = str(config.get("local_embedding_base_url") or config.get("local_llm_base_url") or "")
    model = str(config.get("local_embedding_model") or "")
    if not base_url or not model:
        return None
    return LocalEmbeddingProvider(
        base_url=base_url,
        model=model,
        api_key=str(settings.local_embedding_api_key or config.get("local_llm_api_key") or ""),
        access_client_id=settings.local_llm_access_client_id,
        access_client_secret=settings.local_llm_access_client_secret,
        timeout_seconds=settings.local_embedding_timeout_seconds,
    )


def _knowledge_authority(source_type: str) -> tuple[str, int]:
    normalized = str(source_type or "internal_document").strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized not in SOURCE_AUTHORITY:
        raise HTTPException(422, f"Unknown knowledge source type '{source_type}'.")
    return normalized, SOURCE_AUTHORITY[normalized]


@router.get("")
def agents(
    app_mode: str = "",
    section: str = "",
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    active = resolve_agent_profile(app_mode, section)
    operation = _operation_type(app_mode, active)
    _runtime, _access, _org, _facility, status = build_runtime(engine=engine, settings=settings, context=context, operation_type=operation)
    return {
        "active_agent": _profile_payload(active),
        "agents": [_profile_payload(profile) for profile in PROFILES.values()],
        "provider": _provider_payload(status),
        "workspace": {
            "app_mode": app_mode,
            "section": section,
            "organization_id": context.organization_id,
            "facility_id": context.facility_id,
        },
    }


@router.post("/run")
def run_agent(
    payload: AgentRun,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    profile = _active_profile(payload.agent_key, payload.app_mode, payload.section)
    operation = _operation_type(payload.app_mode, profile)
    runtime, access, organization_name, facility_name, _status = build_runtime(engine=engine, settings=settings, context=context, operation_type=operation)
    result = runtime.run(
        profile=profile,
        access=access,
        question=payload.question.strip(),
        history=[item.model_dump() for item in payload.history][-20:],
        organization_name=organization_name,
        facility_name=facility_name,
    )
    return {**result.as_dict(), "agent": _profile_payload(profile)}


@router.get("/diagnostics")
def ai_diagnostics(
    app_mode: str = "",
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in DIAGNOSTIC_ROLES:
        raise HTTPException(403, "Admin access is required for AI diagnostics.")
    operation = "production" if "production" in app_mode.casefold() else "retail"
    return diagnostics(engine=engine, settings=settings, context=context, operation_type=operation)


@router.get("/telemetry")
def ai_telemetry(
    days: int = 30,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in DIAGNOSTIC_ROLES:
        raise HTTPException(403, "Admin access is required for AI telemetry.")
    return AITelemetry(engine).summary(context.organization_id, context.facility_id, limit_days=max(1, min(int(days), 365)))


@router.post("/knowledge", status_code=201)
async def ingest_knowledge(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    source: str = Form(default=""),
    source_type: str = Form(default="internal_document"),
    authority_level: int = Form(default=0),
    jurisdiction: str = Form(default=""),
    effective_date: str = Form(default=""),
    version: str = Form(default=""),
    source_url: str = Form(default=""),
    facility_scope: bool = Form(default=True),
    global_scope: bool = Form(default=False),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    role = context.role.casefold()
    if role not in KNOWLEDGE_ROLES:
        raise HTTPException(403, "Your role cannot publish AI knowledge sources.")
    normalized_type, derived_authority = _knowledge_authority(source_type)
    if authority_level not in {0, derived_authority}:
        raise HTTPException(422, "Knowledge authority is derived from source type and cannot be self-assigned.")
    if global_scope and role != "dev":
        raise HTTPException(403, "Only Level DEV may publish globally scoped AI knowledge.")
    if not facility_scope and not global_scope and role not in {"dev", "admin"}:
        raise HTTPException(403, "Only Admin or Level DEV may publish organization-wide AI knowledge.")
    if derived_authority == 1:
        if role not in {"dev", "admin"}:
            raise HTTPException(403, "Only Admin or Level DEV may publish government/regulatory sources.")
        if not jurisdiction.strip() or not source_url.strip():
            raise HTTPException(422, "Government/regulatory sources require jurisdiction and source URL.")
    filename = file.filename or "knowledge.txt"
    if Path(filename).suffix.casefold() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(422, "Knowledge sources must be PDF, DOCX, TXT, Markdown, or HTML.")
    payload = await file.read(25 * 1024 * 1024 + 1)
    if len(payload) > 25 * 1024 * 1024:
        raise HTTPException(413, "Knowledge document exceeds the 25 MB limit.")
    service = KnowledgeIngestionService(KnowledgeStore(engine), _embedding_provider(engine, settings))
    try:
        result = service.ingest(
            scope=KnowledgeScope(context.organization_id, context.facility_id),
            filename=filename,
            payload=payload,
            title=title.strip() or filename,
            source=source.strip() or filename,
            source_type=normalized_type,
            authority_level=derived_authority,
            jurisdiction=jurisdiction.strip(),
            effective_date=effective_date.strip(),
            version=version.strip(),
            source_url=source_url.strip(),
            global_scope=bool(global_scope),
            facility_scope=bool(facility_scope),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result


@router.post("/feedback", status_code=201)
def save_feedback(
    payload: FeedbackRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if payload.agent_key.casefold() not in PROFILES:
        raise HTTPException(422, "Unknown AI agent.")
    row_id = AgentFeedbackStore(engine).save(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        agent=payload.agent_key.casefold(),
        task_type=payload.task_type,
        sanitized_prompt=payload.prompt,
        tool_names=payload.tool_names,
        sanitized_tool_outcomes=payload.tool_outcomes,
        answer=payload.answer,
        rating=payload.rating,
        corrected_answer=payload.corrected_answer,
        provider=payload.provider,
        model=payload.model,
    )
    return {"id": row_id, "training_approved": False}
