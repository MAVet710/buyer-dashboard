from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from modules.alpha_mode import AlphaOperatingModeService
from ..auth import RequestContext, get_request_context
from ..database import get_engine


router = APIRouter(prefix="/alpha-operating-mode", tags=["integrations", "alpha"])
ADMIN_ROLES = {"dev", "admin"}


class AlphaOperatingModeSave(BaseModel):
    mode: str = Field(max_length=32)

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized not in {"doobielogic_sandbox", "metrc_sandbox"}:
            raise ValueError("Choose DoobieLogic Sandbox or Metrc Sandbox.")
        return normalized


def _require_admin(context: RequestContext) -> None:
    if context.role.casefold() not in ADMIN_ROLES:
        raise HTTPException(403, "Organization administrator access is required to change the facility operating mode.")


@router.get("")
def current_mode(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        return AlphaOperatingModeService(engine).current(
            context.organization_id,
            context.facility_id,
        ).public()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("")
def set_mode(
    payload: AlphaOperatingModeSave,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_admin(context)
    try:
        return AlphaOperatingModeService(engine).set_mode(
            context.organization_id,
            context.facility_id,
            mode=payload.mode,
            actor=context.user_id,
        ).public()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
