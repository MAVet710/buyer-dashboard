from __future__ import annotations

import pytest

from services.metrc_evaluation_facility_matrix import (
    FAMILY_OPTIONAL_SECTIONS,
    FAMILY_REQUIRED_SECTIONS,
    MetrcFacilityMatrixError,
    optional_execution_instances,
    required_execution_instances,
    required_families_for_operation,
    select_facility_for_operation,
)
from services.metrc_evaluation_workbook import MA_WORKBOOK_TASKS


def _facility(name: str, license_number: str, **caps):
    return {
        "provider_id": license_number,
        "source": {
            "Name": name,
            "LicenseNumber": license_number,
            "FacilityType": caps,
        },
    }


def _rows():
    return [
        _facility("Sandbox Marijuana Cultivator", "GROW", CanGrowPlants=True, CanCreateDerivedPackages=True),
        _facility("Sandbox Marijuana Product Manufacturer", "PROCESSOR", CanInfuseProducts=True, CanCreateDerivedPackages=True),
        _facility("Sandbox Independent Testing Laboratory", "LAB", CanTestPackages=True, CanCreateDerivedPackages=True),
        _facility("Sandbox Marijuana Retailer", "SALES", CanSellToConsumers=True, CanDeliverSalesToConsumers=True, CanCreateDerivedPackages=True),
    ]


def test_permissions_matrix_matches_actual_workbook_d_dependencies() -> None:
    assert FAMILY_REQUIRED_SECTIONS["grow"] == (
        "Locations", "Strains", "Plant Batches / Plants", "Harvests", "Items", "Packages", "GET Transfers / Wholesale"
    )
    assert FAMILY_REQUIRED_SECTIONS["processor"] == (
        "Strains", "Items", "Packages", "GET Transfers / Wholesale"
    )
    assert FAMILY_REQUIRED_SECTIONS["labs"] == (
        "Packages", "Labs", "GET Transfers / Wholesale"
    )
    assert FAMILY_REQUIRED_SECTIONS["sales"] == (
        "Strains", "Items", "Packages", "Sales", "Sales Deliveries", "GET Transfers / Wholesale"
    )
    assert FAMILY_OPTIONAL_SECTIONS["labs"] == (
        "Strains", "Items", "Transfer Template / External Incoming"
    )


def test_shared_d_sections_require_explicit_family_context() -> None:
    assert required_families_for_operation("package_create") == ("grow", "processor", "labs", "sales")
    assert required_families_for_operation("strain_create") == ("grow", "processor", "sales")
    assert required_families_for_operation("transfer_incoming") == ("grow", "processor", "labs", "sales")

    with pytest.raises(MetrcFacilityMatrixError, match="multiple facility families"):
        select_facility_for_operation(operation_type="package_create", facility_records=_rows())


def test_unique_sections_can_select_family_automatically() -> None:
    assert select_facility_for_operation(
        operation_type="plant_batch_plantings", facility_records=_rows()
    )["license_number"] == "GROW"
    assert select_facility_for_operation(
        operation_type="lab_test_record", facility_records=_rows()
    )["license_number"] == "LAB"
    assert select_facility_for_operation(
        operation_type="sales_receipt_create", facility_records=_rows()
    )["license_number"] == "SALES"


def test_processor_shared_section_selects_product_manufacturer_not_grow() -> None:
    selected = select_facility_for_operation(
        operation_type="package_create",
        facility_records=_rows(),
        facility_family="processor",
    )
    assert selected["license_number"] == "PROCESSOR"
    assert selected["facility_family"] == "processor"


def test_workbook_expands_to_86_required_d_execution_instances() -> None:
    required = required_execution_instances(MA_WORKBOOK_TASKS)
    optional = optional_execution_instances(MA_WORKBOOK_TASKS)
    assert len(required) == 86
    assert len(optional) == 26
    assert sum(row["facility_family"] == "grow" for row in required) == 34
    assert sum(row["facility_family"] == "processor" for row in required) == 17
    assert sum(row["facility_family"] == "labs" for row in required) == 12
    assert sum(row["facility_family"] == "sales" for row in required) == 23
