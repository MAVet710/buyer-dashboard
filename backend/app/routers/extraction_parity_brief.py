from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.extraction_brief import generate_extraction_brief
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine
from .extraction_parity import overview

router = APIRouter(
    prefix="/extraction-parity",
    tags=["extraction-parity"],
    dependencies=[Depends(get_production_context)],
)


class ExtractionBriefRequest(BaseModel):
    state: str = Field(default="MA", max_length=64)
    question: str = Field(
        default="Which extraction risks and process opportunities matter most?",
        min_length=2,
        max_length=2000,
    )


@router.post("/doobie-brief")
def doobie_brief(
    payload: ExtractionBriefRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Generate the same grounded run-level brief used by the Streamlit Doobie panel.

    Extraction intentionally stays data-first and uses the local grounded
    extraction brief implementation directly.
    """

    current = overview(context=context, engine=engine)
    runs = current.get("runs") or []
    if not runs:
        raise HTTPException(422, "No extraction run rows are available for the current facility.")

    result = generate_extraction_brief(
        {"runs": runs},
        state=payload.state,
        question=payload.question,
    )
    if not isinstance(result, dict):
        raise HTTPException(500, "Doobie extraction brief returned an invalid response.")
    return result
