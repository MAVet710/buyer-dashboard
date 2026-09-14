from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory.registry import resolve_metrc_base_url
from ..auth import RequestContext
from ..config import Settings
from .metrc_context import resolve_metrc_context
from .metrc_resume_diagnostics import _paged, _reference, _scope_user_id


MAX_CANDIDATES = 5
ENTITY_TYPE = "metrc_evaluation_rebaseline"

PAGED_RESOURCES: tuple[tuple[str, str], ...] = (
    ("locations", "locations/v2/active"),
    ("items", "items/v2/active"),
    ("plant_batches", "plantbatches/v2/active"),
    ("plants_vegetative", "plants/v2/vegetative"),
    ("plants_flowering", "plants/v2/flowering"),
    ("harvests", "harvests/v2/active"),
    ("sales_receipts", "sales/v2/receipts/active"),
    ("sales_deliveries", "sales/v2/deliveries/active"),
    ("transfer_templates", "transfers/v2/templates/outgoing"),
)

REFERENCE_RESOURCES: tuple[tuple[str, str], ...] = (
    ("package_tags_available", "tags/v2/package/available"),
    ("plant_tags_available", "tags/v2/plant/available"),
    ("transfer_types", "transfers/v2/types"),
)


def _candidate(row: dict[str, Any]) -> dict[str, Any]:
    item = row.get("Item") if isinstance(row.get("Item"), dict) else {}
    return {
        "id": row.get("Id") or row.get("id"),
        "label": row.get("Label") or row.get("label") or row.get("Tag") or row.get("tag"),
        "name": row.get("Name") or row.get("name") or item.get("Name") or item.get("name"),
        "status": (
            row.get("Status")
            or row.get("status")
            or row.get("State")
            or row.get("state")
            or row.get("LabTestingState")
        ),
        "last_modified": row.get("LastModified") or row.get("lastModified"),
    }


def _already_completed(engine: Engine, run_id: str) -> bool:
    with Session(engine) as session:
        return session.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == ENTITY_TYPE,
                AuditEvent.entity_id == run_id,
                AuditEvent.action == "completed",
            ).limit(1)
        ) is not None


def _record_completed(
    engine: Engine,
    run_id: str,
    organization_id: str,
    facility_id: str,
    result: dict[str, Any],
) -> None:
    with Session(engine) as session:
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type=ENTITY_TYPE,
                entity_id=run_id,
                action="completed",
                actor="system:metrc-evaluation-rebaseline",
                changes_json=json.dumps(result, sort_keys=True, default=str),
            )
        )
        session.commit()


def run_server_evaluation_rebaseline(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    """Capture GET-only MA sandbox prerequisite evidence without hydrating local ERP state."""

    run_id = str(run_id or "").strip()[:36]
    if not run_id:
        raise ValueError("A rebaseline run ID is required.")
    if _already_completed(engine, run_id):
        return {"run_id": run_id, "status": "already_completed", "read_only": True, "mutations_sent": 0}

    with Session(engine) as session:
        configs = list(
            session.scalars(
                select(IntegrationConfiguration).where(
                    IntegrationConfiguration.provider == "metrc",
                    IntegrationConfiguration.scope_type == "user",
                    IntegrationConfiguration.status == "connected",
                    IntegrationConfiguration.encrypted_secret != "",
                    IntegrationConfiguration.organization_id.is_not(None),
                    IntegrationConfiguration.facility_id.is_not(None),
                )
            )
        )

    base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
    if not base_url or state != "MA" or "sandbox" not in base_url.casefold():
        raise RuntimeError("MA sandbox routing is not verified.")

    facilities: list[dict[str, Any]] = []
    totals = {name: 0 for name, _path in (*PAGED_RESOURCES, *REFERENCE_RESOURCES)}
    seen_licenses: set[str] = set()
    audit_scope: tuple[str, str] | None = None

    for config in configs:
        organization_id = str(config.organization_id or "")
        facility_id = str(config.facility_id or "")
        if not organization_id or not facility_id:
            continue
        context = RequestContext(_scope_user_id(config), organization_id, facility_id, "dev")
        _service, metrc = resolve_metrc_context(engine, settings, context)
        if not (
            metrc.configured
            and metrc.trusted_mapping
            and metrc.environment == "sandbox"
            and metrc.state.upper() == "MA"
            and metrc.license_number
            and metrc.user_api_key
            and metrc.integrator_api_key
        ):
            continue
        if metrc.license_number in seen_licenses:
            continue
        seen_licenses.add(metrc.license_number)
        audit_scope = audit_scope or (organization_id, facility_id)
        auth = (metrc.integrator_api_key, metrc.user_api_key)

        resource_evidence: dict[str, Any] = {}
        for name, path in PAGED_RESOURCES:
            status, rows = _paged(base_url, path, auth, metrc.license_number)
            if status == 200:
                totals[name] += len(rows)
            resource_evidence[name] = {
                "http_status": status,
                "count": len(rows),
                "candidates": [_candidate(row) for row in rows[:MAX_CANDIDATES]],
            }

        for name, path in REFERENCE_RESOURCES:
            status, rows = _reference(base_url, path, auth, metrc.license_number)
            if status == 200:
                totals[name] += len(rows)
            resource_evidence[name] = {
                "http_status": status,
                "count": len(rows),
                "candidates": [_candidate(row) for row in rows[:MAX_CANDIDATES]],
            }

        facilities.append(
            {
                "facility_id": facility_id,
                "license_number": metrc.license_number,
                "resources": resource_evidence,
            }
        )

    if audit_scope is None:
        raise RuntimeError("No trusted MA Metrc sandbox credential contexts were available.")

    result = {
        "schema_version": 1,
        "run_id": run_id,
        "state": "MA",
        "environment": "sandbox",
        "read_only": True,
        "mutations_sent": 0,
        "secrets_included": False,
        "facility_count": len(facilities),
        "totals": totals,
        "facilities": facilities,
    }
    _record_completed(engine, run_id, audit_scope[0], audit_scope[1], result)
    return result
