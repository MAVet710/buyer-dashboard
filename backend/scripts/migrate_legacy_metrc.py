"""Dry-run-first migration of legacy Streamlit METRC settings into the web store.

The Streamlit application persisted per-user METRC credentials in the legacy
``user_integrations`` store. The React/FastAPI application persists encrypted,
facility-scoped records in ``integration_configurations``. This utility bridges
those stores without guessing a facility, exposing credentials in logs, or
overwriting a different web credential.

Dry-run is the default. Pass ``--execute`` only after the aggregate preflight is
clean and the legacy source database is known to be the production source of
truth.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import Engine, create_engine, text

from backend.app.config import get_settings
from modules.coman.db import create_coman_engine
from modules.integrations import IntegrationConfigurationService


MIGRATION_ACTOR = "legacy-metrc-migration"
BLOCKING_ACTIONS = {"ambiguous", "conflict", "incomplete", "orphan"}


@dataclass(frozen=True)
class LegacyMetrcRecord:
    normalized_username: str
    state: str
    license_number: str
    api_key: str

    @property
    def configured(self) -> bool:
        return bool(self.state or self.license_number or self.api_key)

    @property
    def complete(self) -> bool:
        return bool(self.state and self.license_number and self.api_key)


@dataclass(frozen=True)
class DurableUser:
    user_id: str
    normalized_username: str
    role: str
    organization_id: str


@dataclass(frozen=True)
class FacilityCandidate:
    facility_id: str
    organization_id: str
    license_number: str


@dataclass(frozen=True)
class FacilityAssignment:
    user_id: str
    facility_id: str


@dataclass(frozen=True)
class MetrcMigrationPlan:
    action: str
    user_id: str = ""
    organization_id: str = ""
    facility_id: str = ""
    state: str = ""
    license_number: str = ""
    api_key: str = ""


def _normalize_username(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _normalize_database_url(url: str) -> str:
    clean = str(url or "").strip()
    if clean.startswith("postgres://"):
        return "postgresql+psycopg://" + clean[len("postgres://") :]
    if clean.startswith("postgresql://"):
        return "postgresql+psycopg://" + clean[len("postgresql://") :]
    return clean


def _legacy_database_url(explicit_url: str, explicit_path: str, *, prefix: str) -> str:
    env_url = str(os.environ.get(f"{prefix}_DATABASE_URL") or "").strip()
    env_path = str(os.environ.get(f"{prefix}_DB_PATH") or "").strip()
    url = str(explicit_url or env_url).strip()
    path = str(explicit_path or env_path).strip()
    if url and path:
        raise RuntimeError(f"Configure only one {prefix} database URL or path.")
    if url:
        return _normalize_database_url(url)
    if path:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise RuntimeError(f"Configured {prefix} database file does not exist.")
        return f"sqlite:///{resolved.as_posix()}"
    raise RuntimeError(
        f"Legacy source is required. Pass the database URL/path or configure {prefix}_DATABASE_URL/{prefix}_DB_PATH."
    )


def _legacy_engine(url: str) -> Engine:
    options: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **options)


def _read_legacy_records(engine: Engine) -> list[LegacyMetrcRecord]:
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    select normalized_username, metrc_state, metrc_license, metrc_api_key
                    from user_integrations
                    order by normalized_username
                    """
                )
            ).mappings().all()
    except Exception as exc:
        raise RuntimeError("Unable to read the legacy user_integrations METRC fields.") from exc
    return [
        LegacyMetrcRecord(
            normalized_username=_normalize_username(row.get("normalized_username")),
            state=str(row.get("metrc_state") or "").strip(),
            license_number=str(row.get("metrc_license") or "").strip(),
            api_key=str(row.get("metrc_api_key") or "").strip(),
        )
        for row in rows
        if _normalize_username(row.get("normalized_username"))
    ]


def _read_global_metrc_presence(engine: Engine) -> bool:
    """Return only whether legacy global METRC material exists; never return it."""
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    select metrc_state, metrc_license, metrc_api_key
                    from global_integrations
                    where record_key = 'global'
                    limit 1
                    """
                )
            ).mappings().first()
    except Exception as exc:
        raise RuntimeError("Unable to inspect the legacy global_integrations METRC fields.") from exc
    if not row:
        return False
    return bool(
        str(row.get("metrc_state") or "").strip()
        or str(row.get("metrc_license") or "").strip()
        or str(row.get("metrc_api_key") or "").strip()
    )


def _destination_context(engine: Engine) -> tuple[list[DurableUser], list[FacilityCandidate], list[FacilityAssignment], str]:
    with engine.connect() as connection:
        users = connection.execute(
            text(
                """
                select id, normalized_username, role, coalesce(organization_id, '') as organization_id
                from app_users
                where active = true
                order by normalized_username
                """
            )
        ).mappings().all()
        facilities = connection.execute(
            text(
                """
                select id, organization_id, coalesce(license_number, '') as license_number
                from coman_facilities
                where active = true
                order by created_at, id
                """
            )
        ).mappings().all()
        assignments = connection.execute(
            text(
                """
                select r.user_id, r.facility_id
                from app_user_facility_roles r
                join coman_facilities f on f.id = r.facility_id
                where f.active = true
                order by r.created_at, r.id
                """
            )
        ).mappings().all()

    facility_rows = [
        FacilityCandidate(
            facility_id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            license_number=str(row.get("license_number") or "").strip(),
        )
        for row in facilities
    ]
    default_org = facility_rows[0].organization_id if facility_rows else ""
    return (
        [
            DurableUser(
                user_id=str(row["id"]),
                normalized_username=_normalize_username(row.get("normalized_username")),
                role=str(row.get("role") or ""),
                organization_id=str(row.get("organization_id") or ""),
            )
            for row in users
        ],
        facility_rows,
        [FacilityAssignment(user_id=str(row["user_id"]), facility_id=str(row["facility_id"])) for row in assignments],
        default_org,
    )


def _parse_facility_maps(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        username, separator, facility_id = str(value or "").partition("=")
        username = _normalize_username(username)
        facility_id = facility_id.strip()
        if not separator or not username or not facility_id:
            raise RuntimeError("Each --facility-map must be NORMALIZED_USERNAME=FACILITY_ID.")
        if username in result and result[username] != facility_id:
            raise RuntimeError("A legacy username cannot be mapped to two different facilities.")
        result[username] = facility_id
    return result


def _resolve_facility(
    *,
    user: DurableUser,
    legacy_license: str,
    facilities: list[FacilityCandidate],
    assignments: list[FacilityAssignment],
    default_organization_id: str,
    explicit_facility_id: str = "",
) -> FacilityCandidate | None:
    effective_org = user.organization_id or default_organization_id
    org_facilities = [row for row in facilities if row.organization_id == effective_org]
    assigned_ids = {row.facility_id for row in assignments if row.user_id == user.user_id}
    candidates = [row for row in org_facilities if not assigned_ids or row.facility_id in assigned_ids]

    if explicit_facility_id:
        explicit = next((row for row in candidates if row.facility_id == explicit_facility_id), None)
        if explicit is None:
            raise RuntimeError("An explicit facility map points outside the user's authorized active organization/facilities.")
        return explicit

    clean_license = str(legacy_license or "").strip().casefold()
    if clean_license:
        license_matches = [
            row for row in candidates if row.license_number and row.license_number.casefold() == clean_license
        ]
        if len(license_matches) == 1:
            return license_matches[0]

    if len(candidates) == 1:
        return candidates[0]
    return None


def _existing_action(
    service: IntegrationConfigurationService,
    *,
    user_id: str,
    facility_id: str,
    organization_id: str,
    state: str,
    license_number: str,
    api_key: str,
) -> str:
    row = service.get("user", f"{user_id}|{facility_id}", "metrc")
    if row is None:
        return "create"
    public = service.public(row)
    configuration = public.get("configuration", {})
    same = (
        str(row.organization_id or "") == organization_id
        and str(row.facility_id or "") == facility_id
        and str(configuration.get("state") or "").strip() == state
        and str(configuration.get("license_number") or "").strip() == license_number
        and service.secret(row) == api_key
    )
    return "already_migrated" if same else "conflict"


def _build_plans(
    *,
    legacy_records: list[LegacyMetrcRecord],
    users: list[DurableUser],
    facilities: list[FacilityCandidate],
    assignments: list[FacilityAssignment],
    default_organization_id: str,
    facility_maps: dict[str, str],
    service: IntegrationConfigurationService,
) -> list[MetrcMigrationPlan]:
    users_by_name = {user.normalized_username: user for user in users}
    plans: list[MetrcMigrationPlan] = []
    for legacy in legacy_records:
        if not legacy.configured:
            plans.append(MetrcMigrationPlan(action="skip_unconfigured"))
            continue
        if not legacy.complete:
            plans.append(MetrcMigrationPlan(action="incomplete"))
            continue
        user = users_by_name.get(legacy.normalized_username)
        if user is None:
            plans.append(MetrcMigrationPlan(action="orphan"))
            continue
        facility = _resolve_facility(
            user=user,
            legacy_license=legacy.license_number,
            facilities=facilities,
            assignments=assignments,
            default_organization_id=default_organization_id,
            explicit_facility_id=facility_maps.get(legacy.normalized_username, ""),
        )
        if facility is None:
            plans.append(MetrcMigrationPlan(action="ambiguous"))
            continue
        organization_id = user.organization_id or default_organization_id
        action = _existing_action(
            service,
            user_id=user.user_id,
            facility_id=facility.facility_id,
            organization_id=organization_id,
            state=legacy.state,
            license_number=legacy.license_number,
            api_key=legacy.api_key,
        )
        plans.append(
            MetrcMigrationPlan(
                action=action,
                user_id=user.user_id,
                organization_id=organization_id,
                facility_id=facility.facility_id,
                state=legacy.state,
                license_number=legacy.license_number,
                api_key=legacy.api_key,
            )
        )
    return plans


def _summary(plans: list[MetrcMigrationPlan]) -> dict[str, int]:
    actions = (
        "create",
        "already_migrated",
        "skip_unconfigured",
        "ambiguous",
        "conflict",
        "incomplete",
        "orphan",
    )
    return {action: sum(plan.action == action for plan in plans) for action in actions}


def _print_preflight(plans: list[MetrcMigrationPlan], *, execute: bool, global_metrc_present: bool | None) -> None:
    counts = _summary(plans)
    mode = "EXECUTE" if execute else "DRY RUN"
    global_state = "not_checked" if global_metrc_present is None else ("manual_reconciliation_required" if global_metrc_present else "clear")
    print(
        "Legacy METRC preflight "
        f"[{mode}]: records={len(plans)}, create={counts['create']}, already_migrated={counts['already_migrated']}, "
        f"unconfigured={counts['skip_unconfigured']}, ambiguous={counts['ambiguous']}, conflict={counts['conflict']}, "
        f"incomplete={counts['incomplete']}, orphan={counts['orphan']}, global_store={global_state}."
    )


def _execute(plans: list[MetrcMigrationPlan], service: IntegrationConfigurationService) -> int:
    created = 0
    for plan in plans:
        if plan.action != "create":
            continue
        row = service.save(
            scope_type="user",
            scope_key=f"{plan.user_id}|{plan.facility_id}",
            provider="metrc",
            organization_id=plan.organization_id,
            facility_id=plan.facility_id,
            configuration={"state": plan.state, "license_number": plan.license_number},
            secret=plan.api_key,
            actor=MIGRATION_ACTOR,
        )
        public = service.public(row)
        config = public.get("configuration", {})
        if (
            str(row.organization_id or "") != plan.organization_id
            or str(row.facility_id or "") != plan.facility_id
            or str(config.get("state") or "").strip() != plan.state
            or str(config.get("license_number") or "").strip() != plan.license_number
            or service.secret(row) != plan.api_key
        ):
            raise RuntimeError("Post-write METRC migration verification failed.")
        created += 1
    return created


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy Streamlit per-user METRC settings into encrypted facility-scoped web records.")
    parser.add_argument("--legacy-user-database-url", default="", help="Legacy user_integrations database URL. Prefer a read-only credential.")
    parser.add_argument("--legacy-user-db-path", default="", help="Existing legacy user_integrations SQLite file path.")
    parser.add_argument("--legacy-global-database-url", default="", help="Optional legacy global_integrations database URL for global-METRC presence checks.")
    parser.add_argument("--legacy-global-db-path", default="", help="Optional existing legacy global_integrations SQLite file path.")
    parser.add_argument("--facility-map", action="append", default=[], metavar="NORMALIZED_USERNAME=FACILITY_ID", help="Explicitly resolve a genuinely ambiguous user/facility mapping. May be repeated.")
    parser.add_argument("--execute", action="store_true", help="Write only clean create plans. Without this flag the command is read-only.")
    args = parser.parse_args(argv)

    user_source_url = _legacy_database_url(
        args.legacy_user_database_url,
        args.legacy_user_db_path,
        prefix="USER_INTEGRATIONS",
    )
    user_engine = _legacy_engine(user_source_url)
    legacy_records = _read_legacy_records(user_engine)

    global_metrc_present: bool | None = None
    if args.legacy_global_database_url or args.legacy_global_db_path or os.environ.get("GLOBAL_INTEGRATIONS_DATABASE_URL") or os.environ.get("GLOBAL_INTEGRATIONS_DB_PATH"):
        global_url = _legacy_database_url(
            args.legacy_global_database_url,
            args.legacy_global_db_path,
            prefix="GLOBAL_INTEGRATIONS",
        )
        global_metrc_present = _read_global_metrc_presence(_legacy_engine(global_url))

    settings = get_settings()
    destination_engine = create_coman_engine(settings.database_url)
    users, facilities, assignments, default_org = _destination_context(destination_engine)
    facility_maps = _parse_facility_maps(args.facility_map)
    service = IntegrationConfigurationService(destination_engine, settings.integration_encryption_key)
    plans = _build_plans(
        legacy_records=legacy_records,
        users=users,
        facilities=facilities,
        assignments=assignments,
        default_organization_id=default_org,
        facility_maps=facility_maps,
        service=service,
    )
    _print_preflight(plans, execute=args.execute, global_metrc_present=global_metrc_present)

    counts = _summary(plans)
    blockers = sum(counts[action] for action in BLOCKING_ACTIONS)
    if global_metrc_present:
        blockers += 1
    if not args.execute:
        print("Dry run complete. No legacy credential or web integration row was changed.")
        return
    if blockers:
        raise RuntimeError("Execution blocked by unresolved METRC continuity findings. No web integration rows were changed.")

    created = _execute(plans, service)
    print(f"Migrated and post-write verified {created} facility-scoped METRC configuration(s).")


if __name__ == "__main__":
    main()
