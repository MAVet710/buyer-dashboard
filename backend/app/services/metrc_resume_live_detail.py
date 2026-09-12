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
from .metrc_resume_diagnostics import _get, _paged, _reference, _scope_user_id

MAX_CANDIDATES = 20


def _facility_license(row: dict[str, Any]) -> str:
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        value = row.get(key)
        if value:
            return str(value).strip()
    nested = row.get("License") or row.get("license")
    if isinstance(nested, dict):
        for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            value = nested.get(key)
            if value:
                return str(value).strip()
    return ""


def _facility_name(row: dict[str, Any]) -> str:
    for key in ("Name", "DisplayName", "Alias", "name", "displayName"):
        if row.get(key):
            return str(row.get(key)).strip()
    return ""


def _package(row: dict[str, Any]) -> dict[str, Any]:
    item = row.get("Item") if isinstance(row.get("Item"), dict) else {}
    location = row.get("Location") if isinstance(row.get("Location"), dict) else {}
    return {
        "id": row.get("Id") or row.get("id"),
        "label": row.get("Label") or row.get("label"),
        "item": item.get("Name") or item.get("name") or row.get("ItemName"),
        "item_id": item.get("Id") or item.get("id") or row.get("ItemId"),
        "quantity": row.get("Quantity") if row.get("Quantity") is not None else row.get("quantity"),
        "unit": row.get("UnitOfMeasureName") or row.get("UnitOfMeasure") or row.get("unitOfMeasureName"),
        "lab_testing_state": row.get("LabTestingState") or row.get("labTestingState"),
        "lab_testing_state_name": row.get("LabTestingStateName") or row.get("labTestingStateName"),
        "is_finished": row.get("IsFinished") if "IsFinished" in row else row.get("isFinished"),
        "is_on_hold": row.get("IsOnHold") if "IsOnHold" in row else row.get("isOnHold"),
        "is_on_trip": row.get("IsOnTrip") if "IsOnTrip" in row else row.get("isOnTrip"),
        "location": location.get("Name") or location.get("name") or row.get("LocationName"),
        "package_type": row.get("PackageType") or row.get("packageType"),
        "source_package_labels": row.get("SourcePackageLabels") or row.get("sourcePackageLabels"),
        "last_modified": row.get("LastModified") or row.get("lastModified"),
    }


def _transfer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("Id") or row.get("id"),
        "manifest_number": row.get("ManifestNumber") or row.get("manifestNumber"),
        "shipment_type_name": row.get("ShipmentTypeName") or row.get("shipmentTypeName"),
        "name": row.get("Name") or row.get("name"),
        "last_modified": row.get("LastModified") or row.get("lastModified"),
    }


def _reference_name(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("Id") or row.get("id"),
        "name": row.get("Name") or row.get("name"),
        "category": row.get("Category") or row.get("category"),
        "unit": row.get("UnitOfMeasureName") or row.get("Unit") or row.get("unit"),
    }


def _already_completed(engine: Engine, run_id: str) -> bool:
    with Session(engine) as session:
        return session.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == "metrc_resume_detail",
                AuditEvent.entity_id == run_id,
                AuditEvent.action == "completed",
            ).limit(1)
        ) is not None


def run_server_resume_detail(engine: Engine, settings: Settings, run_id: str) -> dict[str, Any]:
    """Persist a sanitized, GET-only live MA sandbox prerequisite inventory."""
    run_id = str(run_id or "").strip()[:36]
    if not run_id:
        raise ValueError("A detail diagnostic run ID is required.")
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

    facilities: list[dict[str, Any]] = []
    seen_licenses: set[str] = set()
    audit_scope: tuple[str, str] | None = None
    true_count = false_count = missing_count = 0

    base_url, state = resolve_metrc_base_url("MA", environment="sandbox")
    if not base_url or state != "MA" or "sandbox" not in base_url.casefold():
        raise RuntimeError("MA sandbox routing is not verified.")

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

        facilities_status, facilities_payload = _get(base_url, "facilities/v2/", auth)
        facility_rows = facilities_payload if isinstance(facilities_payload, list) else []
        provider_facility = next(
            (
                row for row in facility_rows
                if isinstance(row, dict) and _facility_license(row) == metrc.license_number
            ),
            {},
        )
        facility_type = provider_facility.get("FacilityType") if isinstance(provider_facility.get("FacilityType"), dict) else {}
        capability = facility_type.get("CanCreateImmaturePlantPackagesFromPlants") if isinstance(facility_type, dict) else None
        if capability is True:
            true_count += 1
        elif capability is False:
            false_count += 1
        else:
            missing_count += 1

        active_status, active_packages = _paged(base_url, "packages/v2/active", auth, metrc.license_number)
        lab_status, lab_samples = _paged(base_url, "packages/v2/labsamples", auth, metrc.license_number)
        types_status, lab_types = _reference(base_url, "labtests/v2/types", auth, metrc.license_number)
        customer_status, customer_types = _reference(base_url, "sales/v2/customertypes", auth, metrc.license_number)
        incoming_status, incoming = _paged(base_url, "transfers/v2/incoming", auth, metrc.license_number)
        outgoing_status, outgoing = _paged(base_url, "transfers/v2/outgoing", auth, metrc.license_number)
        rejected_status, rejected = _paged(base_url, "transfers/v2/rejected", auth, metrc.license_number)

        facilities.append(
            {
                "facility_id": facility_id,
                "facility_name": _facility_name(provider_facility),
                "license_number": metrc.license_number,
                "facility_type_name": facility_type.get("Name") if isinstance(facility_type, dict) else None,
                "facilities_http": facilities_status,
                "task17_capability": capability,
                "active_packages_http": active_status,
                "active_packages": [_package(row) for row in active_packages[:MAX_CANDIDATES]],
                "lab_samples_http": lab_status,
                "lab_samples": [_package(row) for row in lab_samples[:MAX_CANDIDATES]],
                "lab_types_http": types_status,
                "lab_types": [_reference_name(row) for row in lab_types[:MAX_CANDIDATES]],
                "customer_types_http": customer_status,
                "customer_types": [_reference_name(row) for row in customer_types[:MAX_CANDIDATES]],
                "incoming_http": incoming_status,
                "incoming": [_transfer(row) for row in incoming[:MAX_CANDIDATES]],
                "outgoing_http": outgoing_status,
                "outgoing": [_transfer(row) for row in outgoing[:MAX_CANDIDATES]],
                "rejected_http": rejected_status,
                "rejected": [_transfer(row) for row in rejected[:MAX_CANDIDATES]],
            }
        )

    result = {
        "schema_version": 1,
        "run_id": run_id,
        "state": "MA",
        "environment": "sandbox",
        "read_only": True,
        "mutations_sent": 0,
        "secrets_included": False,
        "facility_count": len(facilities),
        "task17_capability": {"true": true_count, "false": false_count, "missing": missing_count},
        "active_package_total": sum(len(row["active_packages"]) for row in facilities),
        "lab_sample_package_total": sum(len(row["lab_samples"]) for row in facilities),
        "incoming_transfer_total": sum(len(row["incoming"]) for row in facilities),
        "outgoing_transfer_total": sum(len(row["outgoing"]) for row in facilities),
        "rejected_transfer_total": sum(len(row["rejected"]) for row in facilities),
        "facilities": facilities,
    }
    if audit_scope is None:
        raise RuntimeError("No trusted MA Metrc sandbox credential contexts were available.")

    with Session(engine) as session:
        session.add(
            AuditEvent(
                organization_id=audit_scope[0],
                facility_id=audit_scope[1],
                entity_type="metrc_resume_detail",
                entity_id=run_id,
                action="completed",
                actor="system:metrc-resume-detail",
                changes_json=json.dumps(result, sort_keys=True, default=str),
            )
        )
        session.commit()
    return result
