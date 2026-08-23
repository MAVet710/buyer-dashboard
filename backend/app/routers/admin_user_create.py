from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AuditEvent, utc_now
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .admin import UserLink, _link, _require_admin, _serialize_user, _sync_auth_identity, _username, _validate_role

router = APIRouter(prefix="/admin", tags=["admin"])


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    role: str = "buyer"
    organization_id: str = ""
    facility_ids: list[str] = Field(default_factory=list)
    must_change_password: bool = True


def _service_headers(settings: Settings) -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(503, "Supabase administrator user creation is not configured.")
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _create_auth_user(settings: Settings, *, email: str, password: str, display_name: str) -> str:
    request = UrlRequest(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
        data=json.dumps(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"display_name": display_name},
            }
        ).encode(),
        headers=_service_headers(settings),
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code == 422 or exc.code == 400:
            raise HTTPException(409, f"Unable to create the authentication account: {detail}") from exc
        raise HTTPException(502, f"Supabase account creation failed: {detail}") from exc
    except URLError as exc:
        raise HTTPException(502, "Supabase administrator service is unavailable.") from exc
    user_id = str(payload.get("id") or "")
    if not user_id:
        raise HTTPException(502, "Supabase did not return an authentication user ID.")
    return user_id


def _delete_auth_user(settings: Settings, user_id: str) -> None:
    if not user_id:
        return
    try:
        request = UrlRequest(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
            headers=_service_headers(settings),
            method="DELETE",
        )
        with urlopen(request, timeout=10):
            pass
    except Exception:
        # Best-effort rollback only. The durable transaction is still rolled back
        # and a later DEV reconciliation can remove an orphaned Auth identity.
        return


@router.post("/users/create", status_code=201)
def create_user_with_temporary_password(
    payload: UserCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Create the same account shape as Streamlit, backed by Supabase Auth.

    Existing migrated users are never recreated or re-keyed. This endpoint is
    only for a brand-new account created by an authorized admin.
    """

    _require_admin(context)
    role = _validate_role(context, payload.role)
    username, normalized_username = _username(payload.username, payload.username)
    with Session(engine) as session:
        if session.scalar(select(AppUser).where(AppUser.normalized_username == normalized_username)):
            raise HTTPException(409, "That username already exists.")

    contact_email = payload.email.strip().casefold()
    if contact_email and ("@" not in contact_email or contact_email.startswith("@") or contact_email.endswith("@")):
        raise HTTPException(422, "Enter a valid email address or leave Email optional blank.")
    auth_email = contact_email or f"{normalized_username}@users.doobielogic.io"
    auth_user_id = _create_auth_user(
        settings,
        email=auth_email,
        password=payload.password,
        display_name=payload.display_name.strip() or username,
    )

    try:
        link = UserLink(
            auth_user_id=auth_user_id,
            email=auth_email,
            username=username,
            display_name=payload.display_name,
            role=role,
            organization_id=payload.organization_id,
            facility_ids=payload.facility_ids,
        )
        password_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        with Session(engine, expire_on_commit=False) as session, session.begin():
            row, metadata_org_id, metadata_facility_id = _link(session, context, link)
            row.password_hash = password_hash
            row.must_change_password = payload.must_change_password
            row.password_changed_at = utc_now()
            row.updated_by = context.user_id
            session.add(
                AuditEvent(
                    organization_id=context.organization_id,
                    facility_id=context.facility_id,
                    entity_type="app_user",
                    entity_id=row.id,
                    action="user_created_with_temporary_password",
                    actor=context.user_id,
                    changes_json=json.dumps(
                        {
                            "username": username,
                            "role": role,
                            "organization_id": row.organization_id,
                            "facility_ids": payload.facility_ids,
                            "must_change_password": payload.must_change_password,
                        },
                        sort_keys=True,
                    ),
                )
            )
            session.flush()
            snapshot = _serialize_user(session, row)
        _sync_auth_identity(
            settings,
            snapshot,
            organization_id=metadata_org_id,
            facility_id=metadata_facility_id,
        )
        return snapshot
    except Exception:
        _delete_auth_user(settings, auth_user_id)
        raise
