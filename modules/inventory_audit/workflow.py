"""Lifecycle helpers for independent, resumable inventory-audit sessions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json

from sqlalchemy import select

from modules.coman.models import AuditEvent, InventoryAudit


EDITABLE_STATUSES = {"draft", "in_progress", "paused", "stopped"}
CLOSED_STATUSES = {"completed", "cancelled"}
ALL_STATUSES = EDITABLE_STATUSES | CLOSED_STATUSES


class AuditWorkflowError(ValueError):
    """Raised when an inventory-audit lifecycle transition is not allowed."""


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
                    "in_progress": "resumed" if previous in {"paused", "stopped"} else "started",
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
        return list(
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
