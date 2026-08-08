"""Lifecycle helpers for independent, resumable inventory-audit sessions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json

from sqlalchemy import select, text

from modules.coman.models import AuditEvent, InventoryAudit


# Only these states should render an editable scanner. Paused/stopped audits are
# durable and resumable, but remain read-only until the operator explicitly resumes.
EDITABLE_STATUSES = {"draft", "in_progress"}
RESUMABLE_STATUSES = {"paused", "stopped"}
CLOSED_STATUSES = {"completed", "cancelled"}
ALL_STATUSES = EDITABLE_STATUSES | RESUMABLE_STATUSES | CLOSED_STATUSES

# Keep fresh SQLAlchemy-created schemas aligned with migration 0015. Production
# databases are also self-healed by ensure_audit_lifecycle_schema() below so a
# deployed Streamlit app does not get stuck waiting for someone to manually paste
# the standalone SQL into Supabase before Pause/Stop can work.
for _constraint in InventoryAudit.__table__.constraints:
    if getattr(_constraint, "name", None) == "ck_inventory_audit_status":
        _constraint.sqltext = text(
            "status in ('draft', 'in_progress', 'paused', 'stopped', 'completed', 'cancelled')"
        )
        break


class AuditWorkflowError(ValueError):
    """Raised when an inventory-audit lifecycle transition is not allowed."""


def ensure_audit_lifecycle_schema(repository) -> bool:
    """Idempotently apply migration 0015 to a live PostgreSQL audit table.

    Streamlit Cloud deploys application code but does not automatically execute
    the repository's standalone Supabase SQL files. Older production databases
    therefore retain the pre-0015 CHECK constraint and reject ``paused`` and
    ``stopped`` statuses. This guard runs only for PostgreSQL and only changes the
    constraint when the live definition is still missing those states.

    Returns True when the constraint was changed, otherwise False.
    """

    with repository._session_factory.begin() as session:  # noqa: SLF001 - companion module
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return False

        definition = session.execute(
            text(
                """
                select pg_get_constraintdef(c.oid)
                from pg_constraint c
                join pg_class t on t.oid = c.conrelid
                join pg_namespace n on n.oid = t.relnamespace
                where n.nspname = 'public'
                  and t.relname = 'inventory_audits'
                  and c.conname = 'ck_inventory_audit_status'
                """
            )
        ).scalar_one_or_none()

        normalized = str(definition or "").lower()
        changed = "paused" not in normalized or "stopped" not in normalized
        if changed:
            session.execute(
                text(
                    "alter table public.inventory_audits "
                    "drop constraint if exists ck_inventory_audit_status"
                )
            )
            session.execute(
                text(
                    "alter table public.inventory_audits "
                    "add constraint ck_inventory_audit_status "
                    "check (status in ('draft', 'in_progress', 'paused', 'stopped', 'completed', 'cancelled'))"
                )
            )

        # Keep Alembic bookkeeping synchronized when this app-side guard is what
        # actually applied 0015. The update is intentionally conditional so newer
        # databases are never stamped backward.
        session.execute(
            text(
                "update public.alembic_version "
                "set version_num = '0015_inventory_audit_lifecycle' "
                "where version_num = '0014_machine_reference_library'"
            )
        )
        return changed


def set_audit_status(
    repository,
    organization_id: str,
    facility_id: str,
    audit_id: str,
    *,
    status: str,
    actor: str,
    metadata: Mapping[str, object] | None = None,
) -> InventoryAudit:
    """Persist an audit lifecycle transition without coupling it to page state."""

    clean_status = str(status or "").strip().lower()
    if clean_status not in ALL_STATUSES:
        raise AuditWorkflowError(f"Unsupported audit status: {clean_status or 'blank'}")

    # Production may have the audit tables but still be on the pre-0015 status
    # constraint. Repair that schema before attempting Pause/Stop/Resume so the
    # operator is never trapped in an audit because deployment skipped the SQL.
    try:
        ensure_audit_lifecycle_schema(repository)
    except Exception as exc:
        raise AuditWorkflowError(
            "The audit database could not enable Pause/Stop automatically. "
            "Verify the database user can alter inventory_audits or apply migration 0015."
        ) from exc

    with repository._session_factory.begin() as session:  # noqa: SLF001 - companion module
        audit = repository._require_audit(  # noqa: SLF001 - companion module
            session,
            organization_id,
            audit_id,
            facility_id,
        )
        previous = audit.status
        if previous in CLOSED_STATUSES and clean_status != previous:
            raise AuditWorkflowError("Completed or cancelled audits cannot be reopened from the scanner.")
        if previous == clean_status:
            return audit

        audit.status = clean_status
        now = datetime.now(timezone.utc)
        payload = {
            "from": previous,
            "to": clean_status,
            "occurred_at": now.isoformat(),
        }
        if metadata:
            payload.update(dict(metadata))
        session.add(
            AuditEvent(
                organization_id=audit.organization_id,
                facility_id=audit.facility_id,
                entity_type="inventory_audit",
                entity_id=audit.id,
                action={
                    "in_progress": "resumed" if previous in RESUMABLE_STATUSES else "started",
                    "paused": "paused",
                    "stopped": "stopped",
                    "cancelled": "cancelled",
                    "draft": "returned_to_draft",
                    "completed": "completed",
                }[clean_status],
                actor=str(actor),
                changes_json=json.dumps(payload, default=str),
            )
        )
    return audit


def get_audit_events(repository, organization_id: str, audit_id: str):
    """Return the durable lifecycle/event trail for one audit."""

    with repository._session_factory() as session:  # noqa: SLF001 - companion module
        events = list(
            session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.entity_type == "inventory_audit",
                    AuditEvent.entity_id == audit_id,
                )
                .order_by(AuditEvent.occurred_at, AuditEvent.id)
            )
        )
    # The reporting UI historically used ``created_at`` for event-like rows.
    # AuditEvent uses ``occurred_at``; expose a compatibility alias on these
    # detached instances so existing report rendering remains simple.
    for event in events:
        event.created_at = event.occurred_at
    return events
