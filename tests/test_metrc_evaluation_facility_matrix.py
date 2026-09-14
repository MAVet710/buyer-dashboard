from __future__ import annotations

import pytest

import services.metrc_evaluation_facility_matrix as matrix
from services.metrc_evaluation_facility_matrix import (
    FAMILY_OPTIONAL_SECTIONS,
    FAMILY_REQUIRED_SECTIONS,
    MetrcFacilityMatrixError,
    required_families_for_operation,
    select_facility_for_operation,
)


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


def test_permissions_matrix_matches_actual_workbook_access_dependencies() -> None:
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


def test_shared_sections_require_explicit_permission_context_instead_of_guessing() -> None:
    assert required_families_for_operation("package_create") == ("grow", "processor", "labs", "sales")
    assert required_families_for_operation("strain_create") == ("grow", "processor", "sales")
    assert required_families_for_operation("transfer_incoming") == ("grow", "processor", "labs", "sales")

    with pytest.raises(MetrcFacilityMatrixError, match="multiple permission contexts"):
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


def test_permissions_matrix_does_not_expand_46_regulator_actions_into_extra_runs() -> None:
    assert not hasattr(matrix, "required_execution_instances")
    assert not hasattr(matrix, "optional_execution_instances")
