"""Workbook-driven Massachusetts Metrc facility execution matrix.

The Generic Evaluation 10.2025 Permissions worksheet is explicit that every
section marked ``D`` must be completed per applicable facility family.  This
module turns that instruction into executable routing policy so a shared section
such as Packages or Transfers cannot be silently credited only to a Grow
facility.

This module never provisions credentials and never performs provider writes.
"""

from __future__ import annotations

from typing import Any, Iterable

from services.metrc_facility_capabilities import (
    provider_boolean_capabilities,
    provider_facility_license,
)


class MetrcFacilityMatrixError(RuntimeError):
    """Raised when a workbook action cannot be mapped to one exact facility family."""


FACILITY_FAMILIES = ("grow", "processor", "labs", "sales")

# Transcribed from the actual Permissions worksheet.  ``D`` entries are required
# per facility family.  The prose below the grid confirms Sales Deliveries as a
# required Sales dependency even though its individual grid row is visually blank.
FAMILY_REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "grow": (
        "Locations",
        "Strains",
        "Plant Batches / Plants",
        "Harvests",
        "Items",
        "Packages",
        "GET Transfers / Wholesale",
    ),
    "processor": (
        "Strains",
        "Items",
        "Packages",
        "GET Transfers / Wholesale",
    ),
    "labs": (
        "Packages",
        "Labs",
        "GET Transfers / Wholesale",
    ),
    "sales": (
        "Strains",
        "Items",
        "Packages",
        "Sales",
        "Sales Deliveries",
        "GET Transfers / Wholesale",
    ),
}

# ``O`` entries from the same worksheet.  Optional sections do not contribute to
# the D-required execution count unless that optional access is explicitly being
# requested for the facility family.
FAMILY_OPTIONAL_SECTIONS: dict[str, tuple[str, ...]] = {
    "grow": ("Transfer Template / External Incoming",),
    "processor": ("Transfer Template / External Incoming",),
    "labs": ("Strains", "Items", "Transfer Template / External Incoming"),
    "sales": ("Transfer Template / External Incoming",),
}

OPERATION_SECTION: dict[str, str] = {
    # Locations
    "location_create": "Locations",
    "location_update": "Locations",
    "location_get": "Locations",
    # Strains
    "strain_create": "Strains",
    "strain_update": "Strains",
    "strain_get": "Strains",
    # Items
    "item_create": "Items",
    "item_update": "Items",
    "item_get": "Items",
    # Plant Batches / Plants
    "plant_batch_plantings": "Plant Batches / Plants",
    "plant_batch_packages": "Plant Batches / Plants",
    "plant_batch_growthphase": "Plant Batches / Plants",
    "plant_batch_delete": "Plant Batches / Plants",
    "plant_location": "Plant Batches / Plants",
    "plant_plantings": "Plant Batches / Plants",
    "plant_plantbatch_packages": "Plant Batches / Plants",
    "plant_delete": "Plant Batches / Plants",
    "plant_manicure": "Plant Batches / Plants",
    "plant_harvest": "Plant Batches / Plants",
    # Harvest
    "harvest_packages": "Harvests",
    "harvest_waste": "Harvests",
    "harvest_finish": "Harvests",
    "harvest_unfinish": "Harvests",
    # Packages
    "package_create": "Packages",
    "package_item": "Packages",
    "package_adjust": "Packages",
    "package_finish": "Packages",
    "package_unfinish": "Packages",
    # Labs
    "lab_test_record": "Labs",
    # Sales
    "sales_receipt_create": "Sales",
    "sales_receipt_update": "Sales",
    "sales_receipt_delete": "Sales",
    # Sales deliveries
    "sales_delivery_create": "Sales Deliveries",
    "sales_delivery_update": "Sales Deliveries",
    "sales_delivery_complete": "Sales Deliveries",
    # Transfers / wholesale
    "transfer_incoming": "GET Transfers / Wholesale",
    "transfer_outgoing": "GET Transfers / Wholesale",
    "transfer_rejected": "GET Transfers / Wholesale",
    "transfer_deliveries": "GET Transfers / Wholesale",
    "transfer_delivery_packages": "GET Transfers / Wholesale",
    "transfer_delivery_packages_wholesale": "GET Transfers / Wholesale",
    # Transfer templates are optional access for every facility family.
    "transfer_template_create": "Transfer Template / External Incoming",
    "transfer_template_list": "Transfer Template / External Incoming",
    "transfer_template_deliveries": "Transfer Template / External Incoming",
    "transfer_template_update": "Transfer Template / External Incoming",
}

_DEFAULT_FACILITY_NAMES: dict[str, tuple[str, ...]] = {
    "grow": (
        "Sandbox Marijuana Cultivator",
        "Sandbox Medical Marijuana Cultivator",
    ),
    "processor": (
        "Sandbox Marijuana Product Manufacturer",
        "Sandbox Medical Marijuana Product Manufacturer",
    ),
    "labs": (
        "Sandbox Independent Testing Laboratory",
        "Sandbox Medical Independent Testing Laboratory",
        "Sandbox Standards Laboratory",
    ),
    "sales": (
        "Sandbox Marijuana Retailer",
        "Sandbox Medical Marijuana Retailer",
    ),
}


def _source(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    nested = record.get("source")
    return nested if isinstance(nested, dict) else record


def _facility_name(record: Any) -> str:
    row = _source(record)
    for key in ("Name", "name", "FacilityName", "facilityName"):
        token = str(row.get(key) or "").strip()
        if token:
            return token
    return ""


def section_for_operation(operation_type: str) -> str:
    operation = str(operation_type or "").strip().casefold()
    section = OPERATION_SECTION.get(operation)
    if not section:
        raise MetrcFacilityMatrixError(f"No Permissions worksheet section is registered for {operation!r}.")
    return section


def required_families_for_section(section: str) -> tuple[str, ...]:
    return tuple(
        family
        for family in FACILITY_FAMILIES
        if section in FAMILY_REQUIRED_SECTIONS[family]
    )


def optional_families_for_section(section: str) -> tuple[str, ...]:
    return tuple(
        family
        for family in FACILITY_FAMILIES
        if section in FAMILY_OPTIONAL_SECTIONS[family]
    )


def required_families_for_operation(operation_type: str) -> tuple[str, ...]:
    return required_families_for_section(section_for_operation(operation_type))


def optional_families_for_operation(operation_type: str) -> tuple[str, ...]:
    return optional_families_for_section(section_for_operation(operation_type))


def _cap_true(capabilities: dict[str, bool], *names: str) -> bool:
    return any(capabilities.get(name) is True for name in names)


def _family_capability_ok(family: str, record: Any) -> bool:
    caps = provider_boolean_capabilities(record)
    if family == "grow":
        return caps.get("CanGrowPlants") is True
    if family == "processor":
        return _cap_true(caps, "CanInfuseProducts", "CanCreateDerivedPackages")
    if family == "labs":
        return caps.get("CanTestPackages") is True
    if family == "sales":
        return _cap_true(
            caps,
            "CanSellToConsumers",
            "CanSellToPatients",
            "CanSellToCaregivers",
            "CanSellToExternalPatients",
            "CanDeliverSalesToConsumers",
            "CanDeliverSalesToPatients",
        )
    return False


def _operation_capability_ok(operation_type: str, record: Any) -> bool:
    operation = str(operation_type or "").strip().casefold()
    caps = provider_boolean_capabilities(record)
    if operation.startswith(("plant_", "plant_batch_", "harvest_")):
        return caps.get("CanGrowPlants") is True
    if operation == "lab_test_record":
        return caps.get("CanTestPackages") is True
    if operation.startswith("sales_receipt_"):
        return _cap_true(
            caps,
            "CanSellToConsumers",
            "CanSellToPatients",
            "CanSellToCaregivers",
            "CanSellToExternalPatients",
        )
    if operation.startswith("sales_delivery_"):
        return _cap_true(caps, "CanDeliverSalesToConsumers", "CanDeliverSalesToPatients")
    if operation == "package_create" and "CanCreateDerivedPackages" in caps:
        return caps.get("CanCreateDerivedPackages") is True
    return True


def validate_family_for_operation(
    operation_type: str,
    facility_family: str,
    *,
    allow_optional: bool = True,
) -> str:
    operation = str(operation_type or "").strip().casefold()
    family = str(facility_family or "").strip().casefold()
    if family not in FACILITY_FAMILIES:
        raise MetrcFacilityMatrixError(
            f"facility_family must be one of {', '.join(FACILITY_FAMILIES)} for {operation}."
        )
    required = required_families_for_operation(operation)
    optional = optional_families_for_operation(operation) if allow_optional else ()
    if family not in required and family not in optional:
        section = section_for_operation(operation)
        raise MetrcFacilityMatrixError(
            f"{section} is not a D/O permission for facility family {family!r}."
        )
    return family


def resolve_facility_family(
    operation_type: str,
    facility_family: str = "",
    *,
    allow_optional: bool = True,
) -> str:
    """Resolve a family automatically only when the workbook leaves no ambiguity."""

    operation = str(operation_type or "").strip().casefold()
    supplied = str(facility_family or "").strip().casefold()
    if supplied:
        return validate_family_for_operation(operation, supplied, allow_optional=allow_optional)

    required = required_families_for_operation(operation)
    if len(required) == 1:
        return required[0]

    optional = optional_families_for_operation(operation) if allow_optional else ()
    candidates = tuple(dict.fromkeys((*required, *optional)))
    if len(candidates) == 1:
        return candidates[0]

    section = section_for_operation(operation)
    raise MetrcFacilityMatrixError(
        f"{section} applies to multiple facility families ({', '.join(candidates)}). "
        "Pass an explicit facility family so one facility cannot be credited for another family's D requirement."
    )


def select_facility_for_operation(
    *,
    operation_type: str,
    facility_records: list[dict[str, Any]],
    facility_family: str = "",
    explicit_license: str = "",
    allow_optional: bool = True,
) -> dict[str, Any]:
    """Choose one exact authenticated facility for one workbook/family instance."""

    operation = str(operation_type or "").strip().casefold()
    family = resolve_facility_family(operation, facility_family, allow_optional=allow_optional)
    wanted = str(explicit_license or "").strip()

    if wanted:
        matches = [row for row in facility_records if provider_facility_license(row) == wanted]
        if len(matches) != 1:
            raise MetrcFacilityMatrixError(
                f"Expected exactly one GET /facilities/v2 record for {wanted}; observed {len(matches)}."
            )
        row = matches[0]
        if not _family_capability_ok(family, row):
            raise MetrcFacilityMatrixError(
                f"Facility {wanted} does not match the live provider capability profile for family {family}."
            )
        if not _operation_capability_ok(operation, row):
            raise MetrcFacilityMatrixError(
                f"Facility {wanted} does not expose the provider capability profile required for {operation}."
            )
        return {
            "license_number": wanted,
            "facility_name": _facility_name(row),
            "facility_family": family,
            "section": section_for_operation(operation),
            "selection": "explicit",
            "capabilities": provider_boolean_capabilities(row),
        }

    rows_by_name = {_facility_name(row): row for row in facility_records if _facility_name(row)}
    for name in _DEFAULT_FACILITY_NAMES[family]:
        row = rows_by_name.get(name)
        if row is None:
            continue
        if not _family_capability_ok(family, row) or not _operation_capability_ok(operation, row):
            continue
        license_number = provider_facility_license(row)
        if license_number:
            return {
                "license_number": license_number,
                "facility_name": name,
                "facility_family": family,
                "section": section_for_operation(operation),
                "selection": f"dedicated_{family}_facility",
                "capabilities": provider_boolean_capabilities(row),
            }

    # A dedicated-name record is preferred, but an explicitly compatible live
    # facility is safer than hard-failing merely because Metrc renamed a fixture.
    compatible = [
        row
        for row in facility_records
        if _family_capability_ok(family, row) and _operation_capability_ok(operation, row)
    ]
    compatible = sorted(
        compatible,
        key=lambda row: (provider_facility_license(row), _facility_name(row)),
    )
    if len(compatible) == 1:
        row = compatible[0]
        return {
            "license_number": provider_facility_license(row),
            "facility_name": _facility_name(row),
            "facility_family": family,
            "section": section_for_operation(operation),
            "selection": f"unique_live_{family}_candidate",
            "capabilities": provider_boolean_capabilities(row),
        }

    raise MetrcFacilityMatrixError(
        f"Could not select one unambiguous {family} facility for {operation}. "
        "Use the authenticated Facilities response to choose an explicit license for this facility-family instance."
    )


def required_execution_instances(tasks: Iterable[Any]) -> list[dict[str, Any]]:
    """Expand 46 regulator action rows into the D-required facility instances."""

    rows: list[dict[str, Any]] = []
    for task in tasks:
        operation = str(getattr(task, "operation_type", "") or "").strip().casefold()
        if operation == "facilities":
            continue
        section = OPERATION_SECTION.get(operation)
        if not section:
            continue
        for family in required_families_for_section(section):
            rows.append({
                "task_number": int(getattr(task, "number", 0) or 0),
                "operation_type": operation,
                "sheet": str(getattr(task, "sheet", "") or ""),
                "section": section,
                "facility_family": family,
                "requirement": "D",
            })
    return rows


def optional_execution_instances(tasks: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in tasks:
        operation = str(getattr(task, "operation_type", "") or "").strip().casefold()
        if operation == "facilities":
            continue
        section = OPERATION_SECTION.get(operation)
        if not section:
            continue
        for family in optional_families_for_section(section):
            rows.append({
                "task_number": int(getattr(task, "number", 0) or 0),
                "operation_type": operation,
                "sheet": str(getattr(task, "sheet", "") or ""),
                "section": section,
                "facility_family": family,
                "requirement": "O",
            })
    return rows
