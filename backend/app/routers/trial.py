from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization
from modules.integrations import IntegrationConfigurationService
from services.license_validation import validate_license_key
from services.trial_access import issue_trial_token
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/trial", tags=["trial"])


class TrialActivation(BaseModel):
    trial_key: str = Field(min_length=1, max_length=512)


def _doobie_credentials(engine: Engine, settings: Settings) -> tuple[str, str]:
    try:
        service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
        row = service.get("platform", "global", "doobie")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if row is None:
        raise HTTPException(503, "Doobie trial validation is not configured. Level DEV must configure the platform Doobie integration first.")
    configuration = service.public(row).get("configuration") or {}
    base_url = str(configuration.get("base_url") or "").strip().rstrip("/")
    api_key = service.secret(row)
    if not base_url:
        raise HTTPException(503, "Doobie trial validation has no service URL configured.")
    return base_url, api_key


@router.post("/activate")
def activate_trial(
    payload: TrialActivation,
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    base_url, api_key = _doobie_credentials(engine, settings)
    result = validate_license_key(payload.trial_key, base_url=base_url, api_key=api_key)
    if not result.get("ok"):
        reason = str(result.get("reason") or "license_validation_unavailable")
        raise HTTPException(503, f"Trial validation is unavailable: {reason}")
    if not result.get("valid"):
        reason = str(result.get("reason") or "invalid_trial_key")
        raise HTTPException(403, f"Trial key was not accepted: {reason}")

    with Session(engine) as session:
        organization = session.scalar(
            select(Organization).where(
                Organization.slug == "dev-sandbox",
                Organization.active.is_(True),
            )
        )
        if organization is None:
            raise HTTPException(503, "The isolated trial workspace is not configured.")
        facility = session.scalar(
            select(Facility)
            .where(
                Facility.organization_id == organization.id,
                Facility.active.is_(True),
                Facility.retail_enabled.is_(True),
            )
            .order_by(Facility.name)
        )
        if facility is None:
            facility = session.scalar(
                select(Facility)
                .where(Facility.organization_id == organization.id, Facility.active.is_(True))
                .order_by(Facility.name)
            )
        if facility is None:
            raise HTTPException(503, "The isolated trial workspace has no active facility.")

    signing_secret = settings.integration_encryption_key or ("buyer-dash-development-trial" if settings.is_development else "")
    if not signing_secret:
        raise HTTPException(503, "Trial session signing is not configured.")
    token, expires = issue_trial_token(
        secret=signing_secret,
        organization_id=organization.id,
        facility_id=facility.id,
    )
    return {
        "token": token,
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug},
        "facility": {"id": facility.id, "name": facility.name, "code": facility.code},
        "license": {
            "plan": (result.get("payload") or {}).get("plan"),
            "features": (result.get("payload") or {}).get("features", []),
        },
    }
