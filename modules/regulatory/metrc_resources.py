"""Provider-neutral planning and normalization for read-only Metrc resources.

This module never performs a write. It converts a verified jurisdiction +
resource request into an exact Metrc v2 GET path and wraps provider payloads in
a stable regulatory record envelope. Capability and environment gates are
resolved before any network call is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .registry import CapabilityEvidence, capability_evidence, get_jurisdiction, require_capability


class RegulatoryReadError(ValueError):
    """Raised when a regulatory read cannot be proven safe to plan."""


@dataclass(frozen=True)
class MetrcReadResourceSpec:
    name: str
    capability: str
    path: str
    license_scoped: bool = True
    paginated: bool = True
    required_path_parameters: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetrcReadPlan:
    jurisdiction_code: str
    resource: str
    capability: str
    path: str
    params: dict[str, Any]
    evidence: CapabilityEvidence | None

    def public(self) -> dict[str, Any]:
        return {
            "jurisdiction_code": self.jurisdiction_code,
            "resource": self.resource,
            "capability": self.capability,
            "path": self.path,
            "params": dict(self.params),
            "evidence": self.evidence.public() if self.evidence else None,
        }


METRC_READ_RESOURCES: dict[str, MetrcReadResourceSpec] = {
    "facilities": MetrcReadResourceSpec("facilities", "facilities", "facilities/v2/", license_scoped=False, paginated=False),
    "items_active": MetrcReadResourceSpec("items_active", "items", "items/v2/active"),
    "packages_active": MetrcReadResourceSpec("packages_active", "packages", "packages/v2/active"),
    "locations_active": MetrcReadResourceSpec("locations_active", "locations", "locations/v2/active"),
    "lab_results": MetrcReadResourceSpec("lab_results", "lab_tests", "labtests/v2/results"),
    "incoming_transfers": MetrcReadResourceSpec("incoming_transfers", "transfers", "transfers/v2/incoming"),
    "outgoing_transfers": MetrcReadResourceSpec("outgoing_transfers", "transfers", "transfers/v2/outgoing"),
    "transfer_templates_outgoing": MetrcReadResourceSpec(
        "transfer_templates_outgoing", "transfer_templates", "transfers/v2/templates/outgoing"
    ),
    "transfer_deliveries": MetrcReadResourceSpec(
        "transfer_deliveries", "deliveries", "transfers/v2/{transfer_id}/deliveries",
        license_scoped=False, required_path_parameters=("transfer_id",),
    ),
    "delivery_packages": MetrcReadResourceSpec(
        "delivery_packages", "deliveries", "transfers/v2/deliveries/{delivery_id}/packages",
        license_scoped=False, required_path_parameters=("delivery_id",),
    ),
    "wholesale_delivery_packages": MetrcReadResourceSpec(
        "wholesale_delivery_packages", "wholesale_packages",
        "transfers/v2/deliveries/{delivery_id}/packages/wholesale",
        license_scoped=False, required_path_parameters=("delivery_id",),
    ),
    "plant_batches_active": MetrcReadResourceSpec("plant_batches_active", "plant_batches", "plantbatches/v2/active"),
    "plants_vegetative": MetrcReadResourceSpec("plants_vegetative", "plants", "plants/v2/vegetative"),
    "plants_flowering": MetrcReadResourceSpec("plants_flowering", "plants", "plants/v2/flowering"),
    "harvests_active": MetrcReadResourceSpec("harvests_active", "harvests", "harvests/v2/active"),
    "processing_active": MetrcReadResourceSpec("processing_active", "processing_jobs", "processing/v2/active"),
    "sales_receipts_active": MetrcReadResourceSpec("sales_receipts_active", "sales", "sales/v2/receipts/active"),
    "package_tags_available": MetrcReadResourceSpec("package_tags_available", "tags", "tags/v2/package/available"),
    "plant_tags_available": MetrcReadResourceSpec("plant_tags_available", "tags", "tags/v2/plant/available"),
    "transporter_drivers": MetrcReadResourceSpec("transporter_drivers", "transporters", "transporters/v2/drivers"),
    "transporter_vehicles": MetrcReadResourceSpec("transporter_vehicles", "vehicles", "transporters/v2/vehicles"),
}


def list_metrc_read_resources() -> tuple[MetrcReadResourceSpec, ...]:
    return tuple(METRC_READ_RESOURCES.values())


def build_metrc_read_plan(
    *,
    jurisdiction: str,
    resource: str,
    environment: str = "production",
    license_number: str = "",
    path_parameters: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    page_size: int = 20,
    page_number: int = 1,
) -> MetrcReadPlan:
    profile = get_jurisdiction(jurisdiction)
    if profile is None:
        raise RegulatoryReadError("Select a verified Metrc jurisdiction.")
    spec = METRC_READ_RESOURCES.get(str(resource or "").strip())
    if spec is None:
        raise RegulatoryReadError("Select a supported normalized Metrc read resource.")

    try:
        require_capability(profile.code, spec.capability, environment=environment)
    except ValueError as exc:
        raise RegulatoryReadError(str(exc)) from exc

    license_number = str(license_number or "").strip()
    if spec.license_scoped and not license_number:
        raise RegulatoryReadError(f"{spec.name} requires an exact Metrc facility license number.")

    replacements: dict[str, str] = {}
    supplied_path_parameters = path_parameters or {}
    for key in spec.required_path_parameters:
        value = str(supplied_path_parameters.get(key) or "").strip()
        if not value:
            raise RegulatoryReadError(f"{spec.name} requires path parameter {key}.")
        replacements[key] = quote(value, safe="")
    path = spec.path.format(**replacements)

    params: dict[str, Any] = {}
    if spec.license_scoped:
        params["licenseNumber"] = license_number
    if spec.paginated:
        params["pageSize"] = max(1, min(int(page_size), 100))
        params["pageNumber"] = max(1, int(page_number))

    for key, value in (query or {}).items():
        if key == "licenseNumber" and spec.license_scoped and str(value or "").strip() != license_number:
            raise RegulatoryReadError("Query parameters cannot substitute a different Metrc facility license.")
        params[key] = value

    return MetrcReadPlan(
        jurisdiction_code=profile.code,
        resource=spec.name,
        capability=spec.capability,
        path=path,
        params=params,
        evidence=capability_evidence(profile.code, spec.capability),
    )


def payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("Data", "data", "Results", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, dict)]
    return []


def normalize_metrc_payload(*, jurisdiction: str, resource: str, payload: Any) -> list[dict[str, Any]]:
    """Wrap provider records in a stable, lossless regulatory envelope.

    The source record is preserved under ``source`` so resource-specific fields
    are never discarded while callers can rely on a common set of identity and
    status keys across states and resource families.
    """

    profile = get_jurisdiction(jurisdiction)
    if profile is None:
        raise RegulatoryReadError("Select a verified Metrc jurisdiction.")
    if resource not in METRC_READ_RESOURCES:
        raise RegulatoryReadError("Select a supported normalized Metrc read resource.")

    normalized: list[dict[str, Any]] = []
    for row in payload_rows(payload):
        normalized.append({
            "provider": "metrc",
            "jurisdiction_code": profile.code,
            "resource": resource,
            "provider_id": _first_string(row, "Id", "id", "ExternalId", "externalId"),
            "license_number": _first_string(row, "LicenseNumber", "licenseNumber", "FacilityLicenseNumber"),
            "label": _first_string(row, "Label", "label", "Tag", "tag", "PackageLabel"),
            "name": _first_string(row, "Name", "name", "ProductName", "ItemName", "StrainName"),
            "status": _first_string(row, "Status", "status", "State", "state", "PackageState", "LabTestingState"),
            "quantity": _first_value(row, "Quantity", "quantity", "CurrentQuantity", "currentQuantity"),
            "unit_of_measure": _first_string(
                row, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure", "unitOfMeasure"
            ),
            "last_modified": _first_string(
                row, "LastModified", "lastModified", "LastModifiedDateTime", "Modified", "UpdatedAt"
            ),
            "source": row,
        })
    return normalized


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _first_string(row: dict[str, Any], *keys: str) -> str:
    value = _first_value(row, *keys)
    return str(value).strip() if value is not None else ""
