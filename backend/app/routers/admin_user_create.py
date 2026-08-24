from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AuditEvent, utc_now
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from .admin import UserLink, _link, _require_admin, _serialize_user, _username, _validate_role

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

    @field_validator("username", "display_name", "email", "role", "organization_id", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        # Browser/account context can legitimately provide optional values as
        # null during a context refresh. Treat optional text consistently rather
        # than rejecting the whole create-user request before the route can give
        # an actionable validation message.
        return "" if value is None else str(value).strip()

    @field_validator("facility_ids", mode="before")
    @classmethod
    def normalize_facility_ids(cls, value):
        if value is None or value == "":
            return []
        values = value if isinstance(value, (list, tuple, set)) else [value]
        return [str(item).strip() for item in values if item is not None and str(item).strip()]

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        return value.casefold()


def _service_headers(settings: Settings) -> dict[str, str]:
    """Build Supabase admin headers for both modern and legacy server keys.

    Supabase's ``sb_secret_`` keys are API keys, not JWTs, and must not be sent
    as an Authorization bearer token. Legacy ``service_role`` keys are JWTs and
    still require the bearer header for the Auth admin API. Supporting both here
    lets existing deployments migrate keys without breaking user management.
    """

    url = settings.supabase_url.strip()
    key = settings.supabase_service_role_key.strip()
    if not url or not key:
        raise HTTPException(503, "Supabase administrator user creation is not configured.")
    if key.startswith("sb_publishable_"):
        raise HTTPException(503, "Supabase administrator user creation requires a server secret key, not the publishable browser key.")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _credential_error() -> HTTPException:
    return HTTPException(
        502,
        "Supabase rejected the server-side administrator credential. Verify the configured Supabase secret/service-role key belongs to this project's SUPABASE_URL.",
    )


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
        if exc.code in {401, 403}:
            raise _credential_error() from exc
        if exc.code in {400, 422}:
            raise HTTPException(409, f"Unable to create the authentication account: {detail}") from exc
        raise HTTPException(502, f"Supabase account creation failed: {detail}") from exc
    except URLError as exc:
        raise HTTPException(502, "Supabase administrator service is unavailable.") from exc
    user_id = str(payload.get("id") or "")
    if not user_id:
        raise HTTPException(502, "Supabase did not return an authentication user ID.")
    return user_id


def _auth_request(settings: Settings, user_id: str, payload: dict) -> dict:
    request = UrlRequest(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
        data=json.dumps(payload).encode(),
        headers=_service_headers(settings),
        method="PUT",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code in {401, 403}:
            raise _credential_error() from exc
        raise HTTPException(502, f"Supabase account metadata sync failed: {detail}") from exc
    except URLError as exc:
        raise HTTPException(502, "Supabase administrator service is unavailable.") from exc


def _sync_auth_identity(settings: Settings, snapshot: dict, *, organization_id: str, facility_id: str) -> None:
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
    # Synthetic identities must remain valid email addresses even when the
    # legacy username contains characters such as '@' or '+'. Preserve the real
    # username in app_metadata while using a safe local-part for Supabase Auth.
    safe_local_part = "".join(character if character.isalnum() or character in "._-" else "-" for character in normalized_username).strip(".-")
    safe_local_part = safe_local_part or "doobielogic-user"
    auth_email = contact_email or f"{safe_local_part}@users.doobielogic.io"
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
            # Keep the database and Supabase Auth identity atomic from the admin's
            # point of view. If Auth metadata sync fails, session.begin() rolls
            # the durable row back before the best-effort Auth cleanup below.
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
