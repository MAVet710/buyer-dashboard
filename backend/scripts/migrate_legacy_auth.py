"""One-off, idempotent migration of durable legacy users into Supabase Auth.

The durable AppUser UUID is preserved as the Supabase Auth UUID. This keeps
legal acceptance, audit evidence, organization/facility authorization and every
other foreign-key reference attached to the same human account after cutover.

Run with ``--dry-run`` first in production. Dry-run validates every active user,
resolves the organization/facility plan, checks existing Supabase Auth rows, and
reports aggregate create/update counts without changing Postgres or Supabase
Auth.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import urllib.error
import urllib.request

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from modules.coman.db import create_coman_engine
from modules.coman.models import AppUser, AppUserFacilityRole, Facility


@dataclass(frozen=True)
class UserMigrationPlan:
    user_id: str
    username: str
    role: str
    organization_id: str
    facility_id: str
    facility_role_ids: tuple[str, ...]
    email: str
    display_name: str
    password_hash: str
    existing_auth_id: str | None


def _request(url: str, key: str, payload: dict, *, method: str = "POST") -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"},
        method=method,
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


def _plan_user(
    user: AppUser,
    *,
    default_organization_id: str,
    assignment: AppUserFacilityRole | None,
    active_facilities: list[Facility],
    existing_auth_id: str | None,
) -> UserMigrationPlan:
    if not user.password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        raise RuntimeError(f"{user.username} does not have a portable bcrypt password hash")

    organization_id = user.organization_id or default_organization_id
    facilities = [row for row in active_facilities if row.organization_id == organization_id]
    facility_id = assignment.facility_id if assignment else (facilities[0].id if facilities else "")
    if not organization_id or not facility_id:
        raise RuntimeError(f"{user.username} has no usable organization/facility context")

    facility_role_ids: tuple[str, ...] = ()
    if user.role not in {"dev", "admin"} and assignment is None:
        facility_role_ids = tuple(row.id for row in facilities)

    return UserMigrationPlan(
        user_id=user.id,
        username=user.username,
        role=user.role,
        organization_id=organization_id,
        facility_id=facility_id,
        facility_role_ids=facility_role_ids,
        email=_login_email(user),
        display_name=user.display_name or user.username,
        password_hash=user.password_hash,
        existing_auth_id=existing_auth_id,
    )


def _collect_plans(session: Session) -> list[UserMigrationPlan]:
    active_facilities = list(
        session.scalars(select(Facility).where(Facility.active.is_(True)).order_by(Facility.created_at))
    )
    default_organization_id = active_facilities[0].organization_id if active_facilities else ""
    users = list(session.scalars(select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.username)))
    plans: list[UserMigrationPlan] = []

    for user in users:
        assignment = session.scalar(
            select(AppUserFacilityRole)
            .where(AppUserFacilityRole.user_id == user.id)
            .order_by(AppUserFacilityRole.created_at)
        )
        email = _login_email(user)
        existing_auth_id = session.execute(
            text("select id::text from auth.users where id::text = :id or lower(email) = :email limit 1"),
            {"id": user.id, "email": email},
        ).scalar_one_or_none()
        plans.append(
            _plan_user(
                user,
                default_organization_id=default_organization_id,
                assignment=assignment,
                active_facilities=active_facilities,
                existing_auth_id=existing_auth_id,
            )
        )
    return plans


def _print_preflight(plans: list[UserMigrationPlan], *, dry_run: bool) -> None:
    creates = sum(plan.existing_auth_id is None for plan in plans)
    refreshes = len(plans) - creates
    facility_roles = sum(len(plan.facility_role_ids) for plan in plans)
    synthetic_emails = sum(plan.email.endswith("@users.doobielogic.io") for plan in plans)
    role_counts: dict[str, int] = {}
    for plan in plans:
        role_counts[plan.role] = role_counts.get(plan.role, 0) + 1
    roles = ", ".join(f"{role}={count}" for role, count in sorted(role_counts.items())) or "none"
    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(
        f"Legacy auth preflight [{mode}]: users={len(plans)}, create={creates}, refresh={refreshes}, "
        f"facility_roles_to_add={facility_roles}, synthetic_login_emails={synthetic_emails}, roles={roles}."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Migrate durable Buyer Dash users into Supabase Auth.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report the complete migration plan without changing Postgres or Supabase Auth.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_coman_engine(settings.database_url)
    migrated = 0
    updated = 0

    with Session(engine) as session:
        plans = _collect_plans(session)
        _print_preflight(plans, dry_run=args.dry_run)
        if args.dry_run:
            print("Dry run complete. No Supabase Auth users or Buyer Dash access rows were changed.")
            return

        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to execute the auth migration")

        for plan in plans:
            if plan.facility_role_ids:
                for facility_id in plan.facility_role_ids:
                    session.add(
                        AppUserFacilityRole(
                            user_id=plan.user_id,
                            organization_id=plan.organization_id,
                            facility_id=facility_id,
                            role=plan.role,
                        )
                    )

            app_metadata = {
                "app_user_id": plan.user_id,
                "organization_id": plan.organization_id,
                "facility_id": plan.facility_id,
                "role": plan.role,
                "legacy_username": plan.username,
            }
            user_metadata = {"display_name": plan.display_name}

            if plan.existing_auth_id:
                _request(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{plan.existing_auth_id}",
                    settings.supabase_service_role_key,
                    {"app_metadata": app_metadata, "user_metadata": user_metadata},
                    method="PUT",
                )
                updated += 1
            else:
                _request(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                    settings.supabase_service_role_key,
                    {
                        "id": plan.user_id,
                        "email": plan.email,
                        "password_hash": plan.password_hash,
                        "email_confirm": True,
                        "app_metadata": app_metadata,
                        "user_metadata": user_metadata,
                    },
                )
                migrated += 1

            user = session.get(AppUser, plan.user_id)
            if user is None:
                raise RuntimeError(f"Durable user disappeared during auth migration: {plan.user_id}")
            user.email = plan.email
            user.updated_by = "supabase-auth-migration"

        session.commit()

    print(f"Created {migrated} and refreshed {updated} active legacy Supabase Auth accounts.")


if __name__ == "__main__":
    main()
