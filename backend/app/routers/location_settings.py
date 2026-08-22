from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.data_hub_repository import DataHubRepository
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/location-settings", tags=["location-settings"])
DATASET_KEY = "location_settings"
DEFAULTS = {"auto_map_products_during_receive": False, "default_receiving_room": "Receiving"}
WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}


class LocationSettingsUpdate(BaseModel):
    auto_map_products_during_receive: bool = False
    default_receiving_room: str = Field(default="Receiving", max_length=160)


def _load(repository: DataHubRepository, context: RequestContext) -> dict[str, object]:
    source = next(
        (row for row in repository.list_active_sources(context.organization_id, context.facility_id) if str(row.dataset_key) == DATASET_KEY),
        None,
    )
    if source is None:
        return dict(DEFAULTS)
    try:
        parsed = json.loads(source.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **(parsed if isinstance(parsed, dict) else {})}


@router.get("")
def get_location_settings(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    return _load(DataHubRepository(engine), context)


@router.post("")
def save_location_settings(
    payload: LocationSettingsUpdate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role can review location settings but cannot change them.")
    room = payload.default_receiving_room.strip() or "Receiving"
    value = {
        "auto_map_products_during_receive": bool(payload.auto_map_products_during_receive),
        "default_receiving_room": room,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    row = DataHubRepository(engine).publish_source(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        dataset_key=DATASET_KEY,
        dataset_label="Location Settings",
        cache_key="_cache_location_settings",
        filename="location_settings.json",
        fingerprint=sha256(raw).hexdigest(),
        payload=raw,
        inspection={"rows": 1, "columns": len(value), "quality": "Ready", "matches": {}, "missing": []},
        content_type="application/json",
        imported_by_user_id=context.user_id,
        imported_by=context.user_id,
    )
    return {**value, "id": str(row.id)}
