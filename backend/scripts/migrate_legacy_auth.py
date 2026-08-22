"""One-off, idempotent migration of durable legacy users into Supabase Auth."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from modules.coman.db import create_coman_engine
from modules.coman.models import AppUser, AppUserFacilityRole, Facility, Organization


def _request(url: str, key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase Auth import failed ({exc.code}): {detail}") from exc


def _login_email(user: AppUser) -> str:
    if user.email and "@" in user.email:
        return user.email.strip().casefold()
    return f"{user.normalized_username}@users.doobielogic.io"


def main() -> None:
    settings = get_settings()
    engine = create_coman_engine(settings.database_url)
    migrated = 0
    with Session(engine) as session:
        default_facility = session.scalar(select(Facility).where(Facility.active.is_(True)).order_by(Facility.created_at))
        default_org = session.get(Organization, default_facility.organization_id) if default_facility else None
        users = list(session.scalars(select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.username)))
        for user in users:
            if not user.password_hash.startswith(("$2a$", "$2b$", "$2y$")):
                raise RuntimeError(f"{user.username} does not have a portable bcrypt password hash")
            organization_id = user.organization_id or (default_org.id if default_org else "")
            assignment = session.scalar(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == user.id).order_by(AppUserFacilityRole.created_at))
            facilities = list(session.scalars(select(Facility).where(Facility.organization_id == organization_id, Facility.active.is_(True)).order_by(Facility.created_at))) if organization_id else []
            facility_id = assignment.facility_id if assignment else (facilities[0].id if facilities else "")
            if not organization_id or not facility_id:
                raise RuntimeError(f"{user.username} has no usable organization/facility context")
            if user.role != "dev" and assignment is None:
                for facility in facilities:
                    session.add(AppUserFacilityRole(user_id=user.id, organization_id=organization_id, facility_id=facility.id, role=user.role))
            email = _login_email(user)
            _request(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                settings.supabase_service_role_key,
                {
                    "email": email,
                    "password_hash": user.password_hash,
                    "email_confirm": True,
                    "app_metadata": {
                        "app_user_id": user.id,
                        "organization_id": organization_id,
                        "facility_id": facility_id,
                        "role": user.role,
                        "legacy_username": user.username,
                    },
                    "user_metadata": {"display_name": user.display_name or user.username},
                },
            )
            user.email = email
            user.updated_by = "supabase-auth-migration"
            migrated += 1
        session.commit()
    print(f"Migrated {migrated} active legacy accounts to Supabase Auth.")


if __name__ == "__main__":
    main()
