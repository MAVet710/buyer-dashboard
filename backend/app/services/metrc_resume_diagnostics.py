from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import requests
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory.registry import resolve_metrc_base_url
from ..auth import RequestContext
from ..config import Settings
from .metrc_context import resolve_metrc_context

logger = logging.getLogger(__name__)
MAX_PAGE_SIZE = 20
MAX_CANDIDATES = 10
TIMEOUT_SECONDS = 20


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("Data")
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
    return []


def _meta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get("Meta")
    return dict(value) if isinstance(value, dict) else {}


def _alias(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def _json(response: requests.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _get(base_url: str, path: str, auth: tuple[str, str], params: dict[str, Any] | None = None) -> tuple[int, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        auth=auth,
        params=params or {},
        timeout=TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )
    return int(response.status_code), _json(response)


def _paged(base_url: str, path: str, auth: tuple[str, str], license_number: str) -> tuple[int, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        status, payload = _get(
            base_url,
            path,
            auth,
            {"licenseNumber": license_number, "pageNumber": page, "pageSize": MAX_PAGE_SIZE},
        )
        if status != 200:
            return status, records
        records.extend(_rows(payload))
        meta = _meta(payload)
        try:
            total_pages = max(1, int(meta.get("TotalPages") or meta.get("totalPages") or 1))
        except (TypeError, ValueError):
            total_pages = 1
        page += 1
    return 200, records


def _reference(base_url: str, path: str, auth: tuple[str, str], license_number: str) -> tuple[int, list[dict[str, Any]]]:
    status, payload = _get(base_url, path, auth, {"licenseNumber": license_number})
    return status, _rows(payload)


def _package(row: dict[str, Any]) -> dict[str, Any]:
    item = row.get("Item") if isinstance(row.get("Item"), dict) else {}
    return {
        "id": row.get("Id") or row.get("id"),
        "label": row.get("Label") or row.get("label"),
        "item": item.get("Name") or item.get("name") or row.get("ItemName"),
        "quantity": row.get("Quantity") or row.get("quantity"),
        "unit": row.get("UnitOfMeasureName") or row.get("UnitOfMeasure"),
        "lab_testing_state": row.get("LabTestingState") or row.get("labTestingState"),
        "is_finished": row.get("IsFinished") if "IsFinished" in row else row.get("isFinished"),
        "is_on_hold": row.get("IsOnHold") if "IsOnHold" in row else row.get("isOnHold"),
        "last_modified": row.get("LastModified") or row.get("lastModified"),
    }


def _transfer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("Id") or row.get("id"),
        "manifest_number": row.get("ManifestNumber") or row.get("manifestNumber"),
        "last_modified": row.get("LastModified") or row.get("lastModified"),
    }


def _scope_user_id(row: IntegrationConfiguration) -> str:
    scope = str(row.scope_key or "")
    if "|" in scope:
        return scope.split("|", 1)[0].strip()
    return str(row.updated_by or "metrc-resume-diagnostic").strip()


def _already_completed(engine: Engine, run_id: str) -> bool:
    with Session(engine) as session:
        return session.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == "metrc_resume_diagnostic",
                AuditEvent.entity_id == run_id,
                AuditEvent.action == "completed",
            ).limit(1)
        ) is not None


def _record_completed(engine: Engine, run_id: str, organization_id: str, facility_id: str, result: dict[str, Any]) -> None:
    summary = {
        "run_id": run_id,
        "state": result.get("state"),
        "environment": result.get("environment"),
        "facility_count": result.get("facility_count"),
        "active_package_total": result.get("active_package_total"),
        "lab_sample_package_total": result.get("lab_sample_package_total"),
        "incoming_transfer_total": result.get("incoming_transfer_total"),
        "outgoing_transfer_total": result.get("outgoing_transfer_total"),
        "rejected_transfer_total": result.get("rejected_transfer_total"),
        "task17_capability": result.get("task17_capability"),
        "read_only": True,
        "mutations_sent": 0,
    }
    with Session(engine) as session:
        session.add(
            AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="metrc_resume_diagnostic",
                entity_id=run_id,
                action="completed",
                actor="system:metrc-resume-diagnostic",
                changes_json=json.dumps(summary, sort_keys=True),
            )
        )
        session.commit()


def run_server_resume_diagnostic(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    """Run exactly-once, GET-only MA sandbox blocker discovery using stored credentials."""
    run_id = str(run_id or "").strip()[:36]
    if not run_id:
        raise ValueError("A diagnostic run ID is required.")
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

    detailed: list[dict[str, Any]] = []
    seen_licenses: set[str] = set()
    true_count = false_count = missing_count = 0
    active_total = lab_total = incoming_total = outgoing_total = rejected_total = 0
    audit_scope: tuple[str, str] | None = None

    for row in configs:
        organization_id = str(row.organization_id or "")
        facility_id = str(row.facility_id or "")
        if not organization_id or not facility_id:
            continue
        context = RequestContext(_scope_user_id(row), organization_id, facility_id, "dev")
        _service, metrc = resolve_metrc_context(engine, settings, context)
        if not (metrc.configured and metrc.trusted_mapping and metrc.environment == "sandbox"):
            continue
        if metrc.state.upper() != "MA" or not metrc.license_number or metrc.license_number in seen_licenses:
            continue
        if not metrc.user_api_key or not metrc.integrator_api_key:
            continue
        seen_licenses.add(metrc.license_number)
        audit_scope = audit_scope or (organization_id, facility_id)

        base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
        if not base_url or state != "MA" or "sandbox" not in base_url.casefold():
            raise RuntimeError("MA sandbox routing is not verified.")
        auth = (metrc.integrator_api_key, metrc.user_api_key)
        facilities_status, facilities_payload = _get(base_url, "facilities/v2/", auth)
        facility_records = _rows(facilities_payload)
        facility = next(
            (
                item for item in facility_records
                if str(item.get("LicenseNumber") or item.get("licenseNumber") or "").strip() == metrc.license_number
            ),
            {},
        )
        facility_type = facility.get("FacilityType") if isinstance(facility.get("FacilityType"), dict) else {}
        capability = facility_type.get("CanCreateImmaturePlantPackagesFromPlants") if isinstance(facility_type, dict) else None
        if capability is True:
            true_count += 1
        elif capability is False:
            false_count += 1
        else:
            missing_count += 1

        active_status, active = _paged(base_url, "packages/v2/active", auth, metrc.license_number)
        lab_status, labs = _paged(base_url, "packages/v2/labsamples", auth, metrc.license_number)
        types_status, lab_types = _reference(base_url, "labtests/v2/types", auth, metrc.license_number)
        customer_status, customer_types = _reference(base_url, "sales/v2/customertypes", auth, metrc.license_number)
        incoming_status, incoming = _paged(base_url, "transfers/v2/incoming", auth, metrc.license_number)
        outgoing_status, outgoing = _paged(base_url, "transfers/v2/outgoing", auth, metrc.license_number)
        rejected_status, rejected = _paged(base_url, "transfers/v2/rejected", auth, metrc.license_number)

        active_total += len(active)
        lab_total += len(labs)
        incoming_total += len(incoming)
        outgoing_total += len(outgoing)
        rejected_total += len(rejected)
        detailed.append(
            {
                "facility_alias": _alias(metrc.license_number),
                "license_number": metrc.license_number,
                "facilities_http": facilities_status,
                "task17_capability": capability,
                "active_packages_http": active_status,
                "active_packages": [_package(item) for item in active[:MAX_CANDIDATES]],
                "lab_samples_http": lab_status,
                "lab_samples": [_package(item) for item in labs[:MAX_CANDIDATES]],
                "lab_types_http": types_status,
                "lab_types": [
                    {
                        "id": item.get("Id") or item.get("id"),
                        "name": item.get("Name") or item.get("name"),
                        "category": item.get("Category") or item.get("category"),
                        "unit": item.get("UnitOfMeasureName") or item.get("Unit") or item.get("unit"),
                    }
                    for item in lab_types[:MAX_CANDIDATES]
                ],
                "customer_types_http": customer_status,
                "customer_type_count": len(customer_types),
                "incoming_http": incoming_status,
                "incoming": [_transfer(item) for item in incoming[:MAX_CANDIDATES]],
                "outgoing_http": outgoing_status,
                "outgoing": [_transfer(item) for item in outgoing[:MAX_CANDIDATES]],
                "rejected_http": rejected_status,
                "rejected": [_transfer(item) for item in rejected[:MAX_CANDIDATES]],
            }
        )

    result = {
        "schema_version": 1,
        "run_id": run_id,
        "state": "MA",
        "environment": "sandbox",
        "read_only": True,
        "mutations_sent": 0,
        "facility_count": len(detailed),
        "task17_capability": {"true": true_count, "false": false_count, "missing": missing_count},
        "active_package_total": active_total,
        "lab_sample_package_total": lab_total,
        "incoming_transfer_total": incoming_total,
        "outgoing_transfer_total": outgoing_total,
        "rejected_transfer_total": rejected_total,
        "facilities": detailed,
        "secrets_included": False,
    }
    if audit_scope:
        _record_completed(engine, run_id, audit_scope[0], audit_scope[1], result)
    logger.info("METRC_RESUME_DIAGNOSTIC %s", json.dumps(result, sort_keys=True, default=str))
    return result
