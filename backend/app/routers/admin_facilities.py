from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Facility
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/admin/facilities", tags=["admin"])


class FacilityUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    timezone_name: str = Field(default="America/New_York", max_length=64)
    license_number: str = Field(default="", max_length=160)
    license_type: str = Field(default="", max_length=120)
    retail_enabled: bool = True
    production_enabled: bool = False
    cultivation_enabled: bool = False
    commercial_enabled: bool = True
    active: bool = True


def _require_dev(context: RequestContext) -> None:
    if context.role.casefold() != "dev":
        raise HTTPException(403, "Level DEV access is required to edit facility license context.")


def _serialize(row: Facility) -> dict:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "name": row.name,
        "code": row.code,
        "timezone_name": row.timezone_name,
        "license_number": row.license_number,
        "license_type": row.license_type,
        "retail_enabled": row.retail_enabled,
        "production_enabled": row.production_enabled,
        "cultivation_enabled": row.cultivation_enabled,
        "commercial_enabled": row.commercial_enabled,
        "active": row.active,
    }


@router.post("/{facility_id}/update")
def update_facility(
    facility_id: str,
    payload: FacilityUpdate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Edit one durable facility without collapsing distinct license contexts.

    This endpoint exists for migration/cutover correction as well as ongoing
    platform administration. It never changes a facility's organization and it
    records every license/capability change in the durable audit trail.
    """

    _require_dev(context)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        row = session.get(Facility, facility_id)
        if row is None:
            raise HTTPException(404, "Facility was not found.")

        code = payload.code.strip().upper()
        duplicate = session.scalar(
            select(Facility).where(
                Facility.organization_id == row.organization_id,
                Facility.code == code,
                Facility.id != row.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(409, "That facility code already exists in this organization.")

        before = _serialize(row)
        row.name = payload.name.strip()
        row.code = code
        row.timezone_name = payload.timezone_name.strip() or "America/New_York"
        row.license_number = payload.license_number.strip()
        row.license_type = payload.license_type.strip()
        row.retail_enabled = payload.retail_enabled
        row.production_enabled = payload.production_enabled
        row.cultivation_enabled = payload.cultivation_enabled
        row.commercial_enabled = payload.commercial_enabled
        row.active = payload.active
        session.flush()
        after = _serialize(row)

        changes = {
            key: {"before": before[key], "after": after[key]}
            for key in after
            if key not in {"id", "organization_id"} and before[key] != after[key]
        }
        if changes:
            session.add(
                AuditEvent(
                    organization_id=row.organization_id,
                    facility_id=row.id,
                    entity_type="facility",
                    entity_id=row.id,
                    action="facility_context_updated",
                    actor=context.user_id,
                    changes_json=json.dumps(changes, sort_keys=True),
                )
            )

    return after
