import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, AuditEvent, Facility, Organization, utc_now
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/account", tags=["account"])


class UsernameLogin(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


def _invalid_credentials() -> HTTPException:
    # Keep the response intentionally generic so an unauthenticated caller cannot
    # distinguish a missing username from a bad password or disabled account.
    return HTTPException(status_code=400, detail="Invalid login credentials.")


def _supabase_password_session(settings: Settings, email: str, password: str) -> dict:
    """Exchange a linked account email/password for a normal Supabase session."""
    url = settings.supabase_url.strip()
    key = settings.supabase_service_role_key.strip()
    if not url or not key:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable.")

    request = UrlRequest(
        f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": password}).encode("utf-8"),
        headers={"apikey": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {400, 401, 403}:
            raise _invalid_credentials() from exc
        raise HTTPException(status_code=502, detail="Authentication service rejected the sign-in request.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Authentication service is unavailable.") from exc

    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    auth_user_id = str((payload.get("user") or {}).get("id") or "").strip()
    if not access_token or not refresh_token or not auth_user_id:
        raise HTTPException(status_code=502, detail="Authentication service returned an incomplete session.")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "auth_user_id": auth_user_id,
    }


def _facility_payload(row: Facility) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "timezone_name": row.timezone_name,
        "license_number": row.license_number,
        "license_type": row.license_type,
        "capabilities": {
            "retail": row.retail_enabled,
            "production": row.production_enabled,
            "cultivation": row.cultivation_enabled,
            "commercial": row.commercial_enabled,
        },
    }


def _facilities_for_user(session: Session, context: RequestContext, organization_id: str) -> list[Facility]:
    if context.role in {"dev", "admin", "trial"}:
        return list(
            session.scalars(
                select(Facility)
                .where(Facility.organization_id == organization_id, Facility.active.is_(True))
                .order_by(Facility.name)
            )
        )
    return list(
        session.scalars(
            select(Facility)
            .join(AppUserFacilityRole, AppUserFacilityRole.facility_id == Facility.id)
            .where(
                AppUserFacilityRole.user_id == context.user_id,
                AppUserFacilityRole.organization_id == organization_id,
                Facility.active.is_(True),
            )
            .order_by(Facility.name)
        )
    )


@router.post("/username-login")
def username_login(
    payload: UsernameLogin,
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Authenticate a DoobieLogic username without exposing its linked auth email."""
    normalized_username = payload.username.strip().casefold()
    if not normalized_username:
        raise _invalid_credentials()

    with Session(engine) as session:
        user = session.scalar(
            select(AppUser).where(AppUser.normalized_username == normalized_username)
        )
        if not user or not user.active or not str(user.email or "").strip():
            raise _invalid_credentials()
        app_user_id = str(user.id)
        auth_email = str(user.email).strip().casefold()

    auth_session = _supabase_password_session(settings, auth_email, payload.password)
    if auth_session["auth_user_id"] != app_user_id:
        # A valid password was accepted for an identity that is not the durable
        # DoobieLogic user we resolved. Do not issue that mismatched session.
        raise HTTPException(
            status_code=409,
            detail="This account's authentication link is out of sync. Contact an administrator.",
        )

    with Session(engine) as session, session.begin():
        user = session.get(AppUser, app_user_id)
        if user:
            user.last_login_at = utc_now()
            user.updated_by = app_user_id

    return {
        "access_token": auth_session["access_token"],
        "refresh_token": auth_session["refresh_token"],
    }


@router.get("/context")
def account_context(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        organization = session.get(Organization, context.organization_id)
        user = session.get(AppUser, context.user_id)
        facilities = _facilities_for_user(session, context, context.organization_id)
        active_facility = session.get(Facility, context.facility_id)
        capabilities = {
            "retail": bool(active_facility and active_facility.retail_enabled),
            "production": bool(active_facility and active_facility.production_enabled),
            "cultivation": bool(active_facility and active_facility.cultivation_enabled),
            "commercial": bool(active_facility and active_facility.commercial_enabled),
        }
        return {
            "user": {
                "id": context.user_id,
                "display_name": "24-hour Trial" if context.role == "trial" else (user.display_name if user else context.user_id),
                "email": user.email if user else "",
                "role": context.role,
                "must_change_password": bool(user and user.must_change_password),
            },
            "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug} if organization else None,
            "facility_id": context.facility_id,
            "facility": _facility_payload(active_facility) if active_facility else None,
            "capabilities": capabilities,
            "facilities": [_facility_payload(row) for row in facilities],
        }


@router.get("/access-options")
def access_options(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    """Return every organization/facility context the current account may open."""
    with Session(engine) as session:
        if context.role == "dev":
            organizations = list(session.scalars(select(Organization).where(Organization.active.is_(True)).order_by(Organization.name)))
        else:
            organization = session.get(Organization, context.organization_id)
            organizations = [organization] if organization and organization.active else []
        payload = []
        for organization in organizations:
            facilities = _facilities_for_user(session, context, organization.id)
            payload.append(
                {
                    "id": organization.id,
                    "name": organization.name,
                    "slug": organization.slug,
                    "facilities": [_facility_payload(row) for row in facilities],
                }
            )
        return {"organizations": payload, "organization_id": context.organization_id, "facility_id": context.facility_id}


@router.post("/password-changed")
def password_changed(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    """Clear the durable first-login password-change requirement after Supabase succeeds."""
    if context.role == "trial":
        return {"ok": True}
    with Session(engine) as session, session.begin():
        user = session.get(AppUser, context.user_id)
        if user:
            user.must_change_password = False
            user.password_changed_at = utc_now()
            user.updated_by = context.user_id
            session.add(
                AuditEvent(
                    organization_id=context.organization_id,
                    facility_id=context.facility_id,
                    entity_type="app_user",
                    entity_id=context.user_id,
                    action="password_changed",
                    actor=context.user_id,
                    changes_json='{"must_change_password": false}',
                )
            )
    return {"ok": True}
