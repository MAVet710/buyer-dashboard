from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AppUserFacilityRole, AuditEvent, Facility
from services.app_user_store import VALID_ROLES
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/admin", tags=["admin"])


class UserLink(BaseModel):
    auth_user_id: str = Field(min_length=1, max_length=36)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=255)
    role: str = "buyer"
    facility_ids: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str = Field(default="", max_length=255)
    email: str = Field(min_length=3, max_length=320)
    role: str
    facility_ids: list[str]
    active: bool = True


class UserInvite(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=255)
    role: str = "buyer"
    facility_ids: list[str] = Field(default_factory=list)
    redirect_to: str = ""


def _require_admin(context: RequestContext):
    if context.role.casefold() not in {"dev", "admin"}: raise HTTPException(403, "Organization administrator access is required.")


def _validate_role(context: RequestContext, role: str) -> str:
    value = role.strip().casefold()
    if value not in VALID_ROLES: raise HTTPException(422, "Invalid user role.")
    if value == "dev" and context.role != "dev": raise HTTPException(403, "Only Level DEV can grant platform access.")
    return value


def _email(value: str) -> str:
    clean = str(value or "").strip().casefold()
    if "@" not in clean or clean.startswith("@") or clean.endswith("@"): raise HTTPException(422, "A valid email address is required.")
    return clean


def _facilities(session: Session, context: RequestContext, facility_ids: list[str]) -> list[Facility]:
    rows = list(session.scalars(select(Facility).where(Facility.id.in_(sorted(set(facility_ids))), Facility.organization_id == context.organization_id, Facility.active.is_(True)))) if facility_ids else []
    if len(rows) != len(set(facility_ids)): raise HTTPException(422, "One or more facilities are unavailable in this organization.")
    return rows


def _serialize_user(session: Session, row: AppUser) -> dict:
    assignments = list(session.scalars(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == row.id)))
    return {"id": row.id, "email": row.email, "display_name": row.display_name, "role": row.role, "active": row.active, "must_change_password": row.must_change_password, "last_login_at": row.last_login_at, "created_at": row.created_at, "facility_ids": [item.facility_id for item in assignments]}


def _link(session: Session, context: RequestContext, payload: UserLink) -> AppUser:
    role = _validate_role(context, payload.role); facilities = _facilities(session, context, payload.facility_ids)
    email = _email(payload.email); existing = session.scalar(select(AppUser).where(or_(AppUser.id == payload.auth_user_id, AppUser.email == email)))
    if existing and existing.id != payload.auth_user_id: raise HTTPException(409, "That email is already linked to a different authentication account.")
    if existing is None:
        existing = AppUser(id=payload.auth_user_id, organization_id=None if role == "dev" else context.organization_id, username=email, normalized_username=email, display_name=payload.display_name.strip(), email=email, password_hash="supabase-managed", role=role, active=True, must_change_password=False, created_by=context.user_id, updated_by=context.user_id)
        session.add(existing)
    else:
        if existing.organization_id not in {None, context.organization_id} and context.role != "dev": raise HTTPException(403, "That authentication account belongs to another organization.")
        existing.organization_id = None if role == "dev" else context.organization_id; existing.email = email; existing.username = email; existing.normalized_username = email; existing.display_name = payload.display_name.strip(); existing.role = role; existing.active = True; existing.updated_by = context.user_id
        session.query(AppUserFacilityRole).filter(AppUserFacilityRole.user_id == existing.id).delete(synchronize_session=False)
    if role != "dev":
        for facility in facilities: session.add(AppUserFacilityRole(user_id=existing.id, organization_id=context.organization_id, facility_id=facility.id, role=role))
    session.flush(); session.add(AuditEvent(organization_id=context.organization_id, facility_id=context.facility_id, entity_type="app_user", entity_id=existing.id, action="supabase_account_linked", actor=context.user_id, changes_json=json.dumps({"email": email, "role": role, "facility_ids": payload.facility_ids}, sort_keys=True)))
    return existing


@router.get("/users")
def list_users(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_admin(context)
    with Session(engine) as session:
        query = select(AppUser).where(AppUser.organization_id == context.organization_id) if context.role != "dev" else select(AppUser)
        return [_serialize_user(session, row) for row in session.scalars(query.order_by(AppUser.email, AppUser.username))]


@router.post("/users/link", status_code=201)
def link_user(payload: UserLink, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_admin(context)
    with Session(engine) as session, session.begin(): row = _link(session, context, payload); result = _serialize_user(session, row)
    return result


@router.post("/users/invite", status_code=201)
def invite_user(payload: UserInvite, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    _require_admin(context); _validate_role(context, payload.role)
    if not settings.supabase_url or not settings.supabase_service_role_key: raise HTTPException(503, "Supabase administrator invitations are not configured.")
    body = {"email": _email(payload.email), "data": {"display_name": payload.display_name}}
    if payload.redirect_to: body["redirect_to"] = payload.redirect_to
    request = UrlRequest(f"{settings.supabase_url.rstrip('/')}/auth/v1/invite", data=json.dumps(body).encode(), headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=10) as response: auth_user = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]; raise HTTPException(502, f"Supabase invitation failed: {detail}") from exc
    except URLError as exc: raise HTTPException(502, "Supabase invitation service is unavailable.") from exc
    auth_id = str(auth_user.get("id") or "")
    if not auth_id: raise HTTPException(502, "Supabase did not return an authentication user ID.")
    link = UserLink(auth_user_id=auth_id, email=payload.email, display_name=payload.display_name, role=payload.role, facility_ids=payload.facility_ids)
    with Session(engine) as session, session.begin(): row = _link(session, context, link); result = _serialize_user(session, row)
    return result


@router.post("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_admin(context); role = _validate_role(context, payload.role)
    if user_id == context.user_id and not payload.active: raise HTTPException(422, "You cannot deactivate your current account.")
    with Session(engine) as session, session.begin():
        row = session.get(AppUser, user_id)
        if not row or (context.role != "dev" and row.organization_id != context.organization_id): raise HTTPException(404, "User was not found in this organization.")
        facilities = _facilities(session, context, payload.facility_ids); before = {"role": row.role, "active": row.active}
        row.display_name = payload.display_name.strip(); row.email = _email(payload.email); row.username = row.email; row.normalized_username = row.email; row.role = role; row.active = payload.active; row.organization_id = None if role == "dev" else context.organization_id; row.updated_by = context.user_id
        session.query(AppUserFacilityRole).filter(AppUserFacilityRole.user_id == row.id).delete(synchronize_session=False)
        if role != "dev":
            for facility in facilities: session.add(AppUserFacilityRole(user_id=row.id, organization_id=context.organization_id, facility_id=facility.id, role=role))
        session.flush(); session.add(AuditEvent(organization_id=context.organization_id, facility_id=context.facility_id, entity_type="app_user", entity_id=row.id, action="authorization_updated", actor=context.user_id, changes_json=json.dumps({"before": before, "after": {"role": role, "active": payload.active, "facility_ids": payload.facility_ids}}, sort_keys=True))); result = _serialize_user(session, row)
    return result
