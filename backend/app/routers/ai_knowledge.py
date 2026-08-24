from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.ai.retrieval import KnowledgeScope, KnowledgeStore
from services.ai.retrieval.approved_sources import public_catalog, seed_approved_sources

from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .ai_agents import _embedding_provider

router = APIRouter(prefix="/ai-knowledge", tags=["ai-knowledge"])
KNOWLEDGE_ROLES = {"dev", "admin", "supervisor", "qa"}
SEED_ROLES = {"dev", "admin"}


class ApprovedSeedRequest(BaseModel):
    keys: list[str] = Field(default_factory=list, max_length=100)
    force_reindex: bool = False


def _require_knowledge(context: RequestContext) -> None:
    if context.role.casefold() not in KNOWLEDGE_ROLES:
        raise HTTPException(403, "Your role cannot view the AI knowledge library.")


@router.get("")
def knowledge_library(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_knowledge(context)
    scope = KnowledgeScope(context.organization_id, context.facility_id)
    store = KnowledgeStore(engine)
    return {
        "documents": store.list_documents(scope=scope),
        "health": store.health(scope),
    }


@router.get("/approved-sources")
def approved_sources(
    context: RequestContext = Depends(get_request_context),
):
    _require_knowledge(context)
    return public_catalog()


@router.post("/seed-approved")
def seed_approved(
    payload: ApprovedSeedRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in SEED_ROLES:
        raise HTTPException(403, "Admin or Level DEV access is required to seed approved external knowledge.")
    catalog = public_catalog()
    allowed_keys = {str(row.get("key") or "") for row in catalog.get("sources") or []}
    requested = {str(key or "").strip() for key in payload.keys if str(key or "").strip()}
    unknown = sorted(requested - allowed_keys)
    if unknown:
        raise HTTPException(422, f"Unknown approved knowledge source(s): {', '.join(unknown[:10])}")
    store = KnowledgeStore(engine)
    result = seed_approved_sources(
        store=store,
        scope=KnowledgeScope(context.organization_id, context.facility_id),
        embeddings=_embedding_provider(engine, settings),
        keys=requested or None,
        force_reindex=bool(payload.force_reindex),
    )
    result["health"] = store.health(KnowledgeScope(context.organization_id, context.facility_id))
    return result
