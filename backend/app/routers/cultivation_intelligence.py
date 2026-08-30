from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..services.cultivation_intelligence import CultivationIntelligenceService


router = APIRouter(prefix="/production/plants", tags=["cultivation"])


@router.get("/intelligence")
def cultivation_intelligence(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_facility_capability(context, engine, "cultivation")
    return CultivationIntelligenceService(engine).snapshot(
        context.organization_id,
        context.facility_id,
    )
