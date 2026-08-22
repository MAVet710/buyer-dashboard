from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, AuditEvent, Facility, Organization, utc_now
from services.app_user_store import VALID_ROLES
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/admin", tags=["admin"])


class UserLink(BaseModel):
    auth_user_id: str = Field(min_length=1, max_length=36)
    email: str = Field(min_length=3, max_length=320)
    username: str = Field(default="", max_length=120)
    display_name: str = Field(default="", max_length=255)
    role: str = "buyer"
    organization_id: str = ""
    facility_ids: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    username: str = Field(default="", max_length=120)
    display_name: str = Field(default="", max_length=255)
    email: str = Field(min_length=3, max_length=320)
    role: str
    organization_id: str = ""
    facility_ids: list[str]
    active: bool = True
    must_change_password: bool = False


class UserInvite(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    username: str = Field(default="", max_length=120)
    display_name: str = Field(default="", max_length=255)
    role: str = "buyer"
    organization_id: str = ""
    facility_ids: list[str] = Field(default_factory=list)
    redirect_to: str = ""


class PasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=120)


class FacilityCreate(BaseModel):
    organization_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    timezone_name: str = Field(default="America/New_York", max_length=64)
    license_number: str = Field(default="", max_length=160)
    license_type: str = Field(default="", max_length=120)
    retail_enabled: bool = True
    production_enabled: bool = True
    cultivation_enabled: bool = False
    commercial_enabled: bool = True


def _require_admin(context: RequestContext) -> None:
    if context.role.casefold() not in {"dev", "admin"}:
        raise HTTPException(403, "Organization administrator access is required.")


def _require_dev(context: RequestContext) -> None:
    if context.role.casefold() != "dev":
        raise HTTPException(403, "Level DEV access is required.")


def _validate_role(context: RequestContext, role: str) -> str:
    value = str(role or "").strip().casefold()
    if value not in VALID_ROLES:
        raise HTTPException(422, "Invalid user role.")
    if value == "dev" and context.role.casefold() != "dev":
        raise HTTPException(403, "Only Level DEV can grant platform access.")
    return value


def _email(value: str) -> str:
    clean = str(value or "").strip().casefold()
    if "@" not in clean or clean.startswith("@") or clean.endswith("@"):
        raise HTTPException(422, "A valid email address is required.")
    return clean


def _username(value: str, fallback: str) -> tuple[str, str]:
    clean = str(value or "").strip() or str(fallback or "").strip()
    normalized = clean.casefold()
    if not re.fullmatch(r"[a-z0-9._@+-]{1,120}", normalized):
        raise HTTPException(422, "Username contains unsupported characters.")
    return clean, normalized


def _target_organization(session: Session, context: RequestContext, role: str, requested_id: str) -> Organization | None:
    if role == "dev":
        return None
    organization_id = requested_id.strip() if context.role.casefold() == "dev" else context.organization_id
    if not organization_id:
        raise HTTPException(422, "Choose an organization for every non-DEV account.")
    organization = session.get(Organization, organization_id)
    if not organization or not organization.active:
        raise HTTPException(422, "The selected organization is unavailable.")
    if context.role.casefold() != "dev" and organization.id != context.organization_id:
        raise HTTPException(403, "Company administrators cannot manage another organization.")
    return organization


def _facilities(session: Session, organization_id: str, facility_ids: list[str]) -> list[Facility]:
    unique_ids = sorted(set(facility_ids))
    rows = list(
        session.scalars(
            select(Facility).where(
                Facility.id.in_(unique_ids),
                Facility.organization_id == organization_id,
                Facility.active.is_(True),
            )
        )
    ) if unique_ids else []
    if len(rows) != len(unique_ids):
        raise HTTPException(422, "One or more facilities are unavailable in this organization.")
    return rows


def _serialize_user(session: Session, row: AppUser) -> dict:
    assignments = list(session.scalars(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == row.id)))
    return {
        "id": row.id,
        "organization_id": row.organization_id or "",
        "username": row.username,
        "email": row.email,
        "display_name": row.display_name,
        "role": row.role,
        "active": row.active,
        "must_change_password": row.must_change_password,
        "last_login_at": row.last_login_at,
        "created_at": row.created_at,
        "facility_ids": [item.facility_id for item in assignments],
    }


def _auth_request(settings: Settings, user_id: str, payload: dict) -> dict:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "Supabase administrator operations are not configured.")
    request = UrlRequest(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
        data=json.dumps(payload).encode(),
        headers={
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise HTTPException(502, f"Supabase account update failed: {detail}") from exc
    except URLError as exc:
        raise HTTPException(502, "Supabase administrator service is unavailable.") from exc


def _sync_auth_identity(settings: Settings, snapshot: dict, *, organization_id: str, facility_id: str) -> None:
    # Legacy/local test environments intentionally have no Supabase administrator
    # credentials. Linking remains durable locally; production additionally syncs
    # the already-created Supabase identity when those credentials are present.
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    _auth_request(
        settings,
        str(snapshot["id"]),
        {
            "email": snapshot["email"],
            "app_metadata": {
                "app_user_id": snapshot["id"],
                "organization_id": organization_id,
                "facility_id": facility_id,
                "role": snapshot["role"],
                "legacy_username": snapshot["username"],
            },
            "user_metadata": {"display_name": snapshot["display_name"] or snapshot["username"]},
        },
    )


def _link(session: Session, context: RequestContext, payload: UserLink) -> tuple[AppUser, str, str]:
    role = _validate_role(context, payload.role)
    organization = _target_organization(session, context, role, payload.organization_id)
    facilities = [] if role == "dev" else _facilities(session, organization.id, payload.facility_ids)
    if role != "dev" and not facilities:
        raise HTTPException(422, "Assign at least one facility so the user has an operational access context.")
    email = _email(payload.email)
    username, normalized_username = _username(payload.username, email)
    existing = session.scalar(select(AppUser).where(or_(AppUser.id == payload.auth_user_id, AppUser.email == email)))
    if existing and existing.id != payload.auth_user_id:
        raise HTTPException(409, "That email is already linked to a different authentication account.")
    if existing is None:
        existing = AppUser(
            id=payload.auth_user_id,
            organization_id=None if role == "dev" else organization.id,
            username=username,
            normalized_username=normalized_username,
            display_name=payload.display_name.strip(),
            email=email,
            password_hash="supabase-managed",
            role=role,
            active=True,
            must_change_password=False,
            created_by=context.user_id,
            updated_by=context.user_id,
        )
        session.add(existing)
    else:
        if existing.organization_id not in {None, context.organization_id} and context.role.casefold() != "dev":
            raise HTTPException(403, "That authentication account belongs to another organization.")
        existing.organization_id = None if role == "dev" else organization.id
        existing.email = email
        existing.username = username
        existing.normalized_username = normalized_username
        existing.display_name = payload.display_name.strip()
        existing.role = role
        existing.active = True
        existing.updated_by = context.user_id
        session.query(AppUserFacilityRole).filter(AppUserFacilityRole.user_id == existing.id).delete(synchronize_session=False)
    if role != "dev":
        for facility in facilities:
            session.add(AppUserFacilityRole(user_id=existing.id, organization_id=organization.id, facility_id=facility.id, role=role))
    session.flush()
    metadata_org_id = context.organization_id if role == "dev" else organization.id
    metadata_facility_id = context.facility_id if role == "dev" else facilities[0].id
    session.add(
        AuditEvent(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_type="app_user",
            entity_id=existing.id,
            action="supabase_account_linked",
            actor=context.user_id,
            changes_json=json.dumps({"email": email, "role": role, "organization_id": organization.id if organization else None, "facility_ids": payload.facility_ids}, sort_keys=True),
        )
    )
    return existing, metadata_org_id, metadata_facility_id


@router.get("/users")
def list_users(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_admin(context)
    with Session(engine) as session:
        query = select(AppUser).where(AppUser.organization_id == context.organization_id) if context.role.casefold() != "dev" else select(AppUser)
        return [_serialize_user(session, row) for row in session.scalars(query.order_by(AppUser.username))]


@router.get("/organizations")
def list_organizations(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_dev(context)
    with Session(engine) as session:
        organizations = list(session.scalars(select(Organization).order_by(Organization.name)))
        result = []
        for organization in organizations:
            facilities = list(session.scalars(select(Facility).where(Facility.organization_id == organization.id).order_by(Facility.name)))
            result.append({
                "id": organization.id,
                "name": organization.name,
                "slug": organization.slug,
                "active": organization.active,
                "facilities": [{
                    "id": facility.id,
                    "name": facility.name,
                    "code": facility.code,
                    "timezone_name": facility.timezone_name,
                    "license_number": facility.license_number,
                    "license_type": facility.license_type,
                    "active": facility.active,
                    "retail_enabled": facility.retail_enabled,
                    "production_enabled": facility.production_enabled,
                    "cultivation_enabled": facility.cultivation_enabled,
                    "commercial_enabled": facility.commercial_enabled,
                } for facility in facilities],
            })
        return result


@router.post("/organizations", status_code=201)
def create_organization(payload: OrganizationCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_dev(context)
    slug = re.sub(r"[^a-z0-9-]+", "-", payload.slug.strip().casefold()).strip("-")
    if not slug:
        raise HTTPException(422, "Organization slug is required.")
    with Session(engine) as session, session.begin():
        if session.scalar(select(Organization).where(Organization.slug == slug)):
            raise HTTPException(409, "That organization slug already exists.")
        row = Organization(name=payload.name.strip(), slug=slug, active=True)
        session.add(row)
        session.flush()
        return {"id": row.id, "name": row.name, "slug": row.slug, "active": row.active}


@router.post("/facilities", status_code=201)
def create_facility(payload: FacilityCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_dev(context)
    with Session(engine) as session, session.begin():
        organization = session.get(Organization, payload.organization_id)
        if not organization or not organization.active:
            raise HTTPException(422, "The selected organization is unavailable.")
        code = payload.code.strip().upper()
        if session.scalar(select(Facility).where(Facility.organization_id == organization.id, Facility.code == code)):
            raise HTTPException(409, "That facility code already exists in this organization.")
        row = Facility(
            organization_id=organization.id,
            name=payload.name.strip(),
            code=code,
            timezone_name=payload.timezone_name.strip() or "America/New_York",
            license_number=payload.license_number.strip(),
            license_type=payload.license_type.strip(),
            retail_enabled=payload.retail_enabled,
            production_enabled=payload.production_enabled,
            cultivation_enabled=payload.cultivation_enabled,
            commercial_enabled=payload.commercial_enabled,
            active=True,
        )
        session.add(row)
        session.flush()
        return {"id": row.id, "organization_id": row.organization_id, "name": row.name, "code": row.code}


@router.post("/users/link", status_code=201)
def link_user(payload: UserLink, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    _require_admin(context)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        row, metadata_org_id, metadata_facility_id = _link(session, context, payload)
        snapshot = _serialize_user(session, row)
    _sync_auth_identity(settings, snapshot, organization_id=metadata_org_id, facility_id=metadata_facility_id)
    return snapshot


@router.post("/users/invite", status_code=201)
def invite_user(payload: UserInvite, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    _require_admin(context)
    _validate_role(context, payload.role)
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "Supabase administrator invitations are not configured.")
    body = {"email": _email(payload.email), "data": {"display_name": payload.display_name}}
    if payload.redirect_to:
        body["redirect_to"] = payload.redirect_to
    request = UrlRequest(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/invite",
        data=json.dumps(body).encode(),
        headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            auth_user = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise HTTPException(502, f"Supabase invitation failed: {detail}") from exc
    except URLError as exc:
        raise HTTPException(502, "Supabase invitation service is unavailable.") from exc
    auth_id = str(auth_user.get("id") or "")
    if not auth_id:
        raise HTTPException(502, "Supabase did not return an authentication user ID.")
    link = UserLink(auth_user_id=auth_id, email=payload.email, username=payload.username, display_name=payload.display_name, role=payload.role, organization_id=payload.organization_id, facility_ids=payload.facility_ids)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        row, metadata_org_id, metadata_facility_id = _link(session, context, link)
        snapshot = _serialize_user(session, row)
    _sync_auth_identity(settings, snapshot, organization_id=metadata_org_id, facility_id=metadata_facility_id)
    return snapshot


@router.post("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    _require_admin(context)
    role = _validate_role(context, payload.role)
    if user_id == context.user_id and not payload.active:
        raise HTTPException(422, "You cannot deactivate your current account.")
    with Session(engine, expire_on_commit=False) as session, session.begin():
        row = session.get(AppUser, user_id)
        if not row or (context.role.casefold() != "dev" and row.organization_id != context.organization_id):
            raise HTTPException(404, "User was not found in this organization.")
        if user_id == context.user_id and role != row.role:
            raise HTTPException(422, "You cannot change the role of the account currently signed in.")
        organization = _target_organization(session, context, role, payload.organization_id)
        facilities = [] if role == "dev" else _facilities(session, organization.id, payload.facility_ids)
        if role != "dev" and not facilities:
            raise HTTPException(422, "Assign at least one facility so the user has an operational access context.")
        before = {"role": row.role, "active": row.active, "organization_id": row.organization_id}
        username, normalized_username = _username(payload.username, row.username or payload.email)
        row.username = username
        row.normalized_username = normalized_username
        row.display_name = payload.display_name.strip()
        row.email = _email(payload.email)
        row.role = role
        row.active = payload.active
        row.must_change_password = payload.must_change_password
        row.organization_id = None if role == "dev" else organization.id
        row.updated_by = context.user_id
        session.query(AppUserFacilityRole).filter(AppUserFacilityRole.user_id == row.id).delete(synchronize_session=False)
        if role != "dev":
            for facility in facilities:
                session.add(AppUserFacilityRole(user_id=row.id, organization_id=organization.id, facility_id=facility.id, role=role))
        session.flush()
        metadata_org_id = context.organization_id if role == "dev" else organization.id
        metadata_facility_id = context.facility_id if role == "dev" else facilities[0].id
        session.add(AuditEvent(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_type="app_user",
            entity_id=row.id,
            action="authorization_updated",
            actor=context.user_id,
            changes_json=json.dumps({"before": before, "after": {"role": role, "active": payload.active, "organization_id": row.organization_id, "facility_ids": payload.facility_ids, "must_change_password": payload.must_change_password}}, sort_keys=True),
        ))
        snapshot = _serialize_user(session, row)
    _sync_auth_identity(settings, snapshot, organization_id=metadata_org_id, facility_id=metadata_facility_id)
    return snapshot


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: str, payload: PasswordReset, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    _require_admin(context)
    with Session(engine) as session:
        row = session.get(AppUser, user_id)
        if not row or (context.role.casefold() != "dev" and row.organization_id != context.organization_id):
            raise HTTPException(404, "User was not found in this organization.")
        if row.role == "dev" and context.role.casefold() != "dev":
            raise HTTPException(403, "Only Level DEV can reset a DEV account password.")
    if settings.supabase_url and settings.supabase_service_role_key:
        _auth_request(settings, user_id, {"password": payload.password})
    password_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with Session(engine) as session, session.begin():
        row = session.get(AppUser, user_id)
        row.password_hash = password_hash
        row.must_change_password = True
        row.password_changed_at = utc_now()
        row.updated_by = context.user_id
        session.add(AuditEvent(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_type="app_user",
            entity_id=user_id,
            action="password_reset_by_admin",
            actor=context.user_id,
            changes_json='{"must_change_password": true}',
        ))
    return {"ok": True, "must_change_password": True}
