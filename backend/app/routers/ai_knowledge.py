from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.ai.retrieval import KnowledgeScope, KnowledgeStore
from services.ai.retrieval.approved_sources import public_catalog, seed_approved_sources
from services.ai.retrieval.curated_sources import public_curated_catalog, seed_curated_sources

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


def _combined_catalog() -> dict:
    approved = public_catalog()
    curated = public_curated_catalog()
    return {
        "schema_version": max(int(approved.get("schema_version") or 1), int(curated.get("schema_version") or 1)),
        "reviewed_at": max(str(approved.get("reviewed_at") or ""), str(curated.get("reviewed_at") or "")),
        "sources": [*(approved.get("sources") or []), *(curated.get("sources") or [])],
    }


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
    return _combined_catalog()


@router.post("/seed-approved")
def seed_approved(
    payload: ApprovedSeedRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in SEED_ROLES:
        raise HTTPException(403, "Admin or Level DEV access is required to seed approved external knowledge.")

    catalog = _combined_catalog()
    allowed_keys = {str(row.get("key") or "") for row in catalog.get("sources") or []}
    requested = {str(key or "").strip() for key in payload.keys if str(key or "").strip()}
    unknown = sorted(requested - allowed_keys)
    if unknown:
        raise HTTPException(422, f"Unknown approved knowledge source(s): {', '.join(unknown[:10])}")

    approved_keys = {str(row.get("key") or "") for row in public_catalog().get("sources") or []}
    curated_keys = {str(row.get("key") or "") for row in public_curated_catalog().get("sources") or []}
    requested_approved = requested & approved_keys
    requested_curated = requested & curated_keys

    store = KnowledgeStore(engine)
    scope = KnowledgeScope(context.organization_id, context.facility_id)
    embeddings = _embedding_provider(engine, settings)
    parts: list[dict] = []

    if not requested or requested_approved:
        parts.append(
            seed_approved_sources(
                store=store,
                scope=scope,
                embeddings=embeddings,
                keys=requested_approved or None,
                force_reindex=bool(payload.force_reindex),
            )
        )
    if not requested or requested_curated:
        parts.append(
            seed_curated_sources(
                store=store,
                scope=scope,
                embeddings=embeddings,
                keys=requested_curated or None,
                force_reindex=bool(payload.force_reindex),
            )
        )

    result = {
        "indexed": sum(int(part.get("indexed") or 0) for part in parts),
        "unchanged": sum(int(part.get("unchanged") or 0) for part in parts),
        "failed": sum(int(part.get("failed") or 0) for part in parts),
        "results": [row for part in parts for row in part.get("results") or []],
        "health": store.health(scope),
    }
    return result
