from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from services.ai.retrieval import KnowledgeScope, KnowledgeStore

from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/ai-knowledge", tags=["ai-knowledge"])
KNOWLEDGE_ROLES = {"dev", "admin", "supervisor", "qa"}


@router.get("")
def knowledge_library(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in KNOWLEDGE_ROLES:
        raise HTTPException(403, "Your role cannot view the AI knowledge library.")
    scope = KnowledgeScope(context.organization_id, context.facility_id)
    store = KnowledgeStore(engine)
    return {
        "documents": store.list_documents(scope=scope),
        "health": store.health(scope),
    }
