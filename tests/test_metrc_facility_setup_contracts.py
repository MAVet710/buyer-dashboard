from __future__ import annotations

import pytest

from modules.regulatory.facility_setup_contracts import (
    build_facility_setup_payload,
    get_facility_setup_action,
    list_facility_setup_actions,
)


def test_facility_setup_catalog_exposes_master_data_without_enabling_dispatch():
    rows = {row.operation_type: row for row in list_facility_setup_actions()}
    for operation in (
        "location_create",
        "sublocation_create",
        "strain_create",
        "item_create",
        "brand_create",
        "processing_job_type_create",
        "additive_template_create",
        "driver_create",
        "vehicle_create",
    ):
        assert operation in rows
    assert all(row.dispatch_enabled is False for row in rows.values())
    assert rows["location_create"].required_permission == "Manage Locations"


def test_facility_setup_complex_action_permissions_match_provider_contracts():
    rows = {row.operation_type: row for row in list_facility_setup_actions()}
    assert rows["item_create"].required_permission == "Manage Items"
    assert rows["processing_job_type_create"].required_permission == "Manage Processing Job"
    assert rows["additive_template_create"].required_permission == "Manage Additives"
    assert rows["driver_create"].required_permission == "Manage Transporters"
    assert rows["vehicle_create"].required_permission == "Manage Transporters"


def test_location_create_payload_is_deterministic():
    body = build_facility_setup_payload(
        "location_create",
        {"name": "Flower Room 2", "location_type_name": "Default", "unexpected": "drop me"},
    )
    assert body == [{"Name": "Flower Room 2", "LocationTypeName": "Default"}]


def test_location_update_payload_requires_provider_identity():
    with pytest.raises(ValueError, match="Location ID"):
        build_facility_setup_payload(
            "location_update",
            {"name": "Flower Room 2", "location_type_name": "Default"},
        )


def test_sublocation_payload_does_not_invent_parent_location_field():
    body = build_facility_setup_payload("sublocation_create", {"name": "Rack A / Shelf 2", "location_id": 99})
    assert body == [{"Name": "Rack A / Shelf 2"}]


def test_strain_payload_is_bounded_to_reviewed_fields():
    body = build_facility_setup_payload(
        "strain_create",
        {
            "name": "GMO",
            "testing_status": "None",
            "thc_level": 24.1,
            "cbd_level": 0.2,
            "indica_percentage": 70,
            "sativa_percentage": 30,
            "unexpected": "must not pass through",
        },
    )
    assert body == [{
        "Name": "GMO",
        "TestingStatus": "None",
        "ThcLevel": 24.1,
        "CbdLevel": 0.2,
        "IndicaPercentage": 70,
        "SativaPercentage": 30,
    }]


def test_item_create_payload_is_bounded_and_coerces_documented_numbers():
    body = build_facility_setup_payload(
        "item_create",
        {
            "name": "GMO Flower 3.5g",
            "item_category": "Buds",
            "unit_of_measure": "Each",
            "strain": "GMO",
            "item_brand": "DoobieLogic Reserve",
            "description": "Premium flower",
            "unit_thc_content": "27.4",
            "unit_thc_content_unit_of_measure": "Percent",
            "unit_weight": "3.5",
            "unit_weight_unit_of_measure": "Grams",
            "processing_job_type_name": "Trim & Cure",
            "unexpected": "must not pass through",
        },
    )
    assert body == [{
        "Name": "GMO Flower 3.5g",
        "ItemCategory": "Buds",
        "UnitOfMeasure": "Each",
        "Strain": "GMO",
        "ItemBrand": "DoobieLogic Reserve",
        "UnitThcContent": 27.4,
        "UnitThcContentUnitOfMeasure": "Percent",
        "UnitWeight": 3.5,
        "UnitWeightUnitOfMeasure": "Grams",
        "Description": "Premium flower",
        "ProcessingJobTypeName": "Trim & Cure",
    }]


def test_item_update_requires_numeric_id_and_keeps_file_ids_bounded():
    body = build_facility_setup_payload(
        "item_update",
        {
            "id": "321",
            "name": "GMO Flower 3.5g",
            "item_category": "Buds",
            "unit_of_measure": "Each",
            "product_image_file_system_ids": [4, "5"],
            "unexpected_file_id": 999,
        },
    )
    assert body == [{
        "Id": 321,
        "Name": "GMO Flower 3.5g",
        "ItemCategory": "Buds",
        "UnitOfMeasure": "Each",
        "ProductImageFileSystemIds": [4, 5],
    }]
    with pytest.raises(ValueError, match="Item ID must be numeric"):
        build_facility_setup_payload(
            "item_update",
            {"id": "nope", "name": "Item", "item_category": "Buds", "unit_of_measure": "Each"},
        )


def test_brand_create_and_update_use_only_name_and_provider_id():
    assert build_facility_setup_payload("brand_create", {"name": "Reserve", "other": "drop"}) == [{"Name": "Reserve"}]
    assert build_facility_setup_payload("brand_update", {"id": "7", "name": "Reserve 2", "other": "drop"}) == [{"Id": 7, "Name": "Reserve 2"}]


def test_processing_job_type_create_and_update_translate_category_field():
    create = build_facility_setup_payload(
        "processing_job_type_create",
        {
            "name": "Infuse Brownies",
            "description": "Turn extract into brownies",
            "category": "Infused Edibles",
            "processing_steps": "Mix, bake, cool",
            "attributes": ["Infuse", "Cooking"],
            "unexpected": "drop",
        },
    )
    assert create == [{
        "Name": "Infuse Brownies",
        "Description": "Turn extract into brownies",
        "Category": "Infused Edibles",
        "ProcessingSteps": "Mix, bake, cool",
        "Attributes": ["Infuse", "Cooking"],
    }]

    update = build_facility_setup_payload(
        "processing_job_type_update",
        {
            "id": 44,
            "name": "Infuse Brownies v2",
            "description": "Updated process",
            "category": "Infused Edibles",
            "processing_steps": "Mix, bake, cool, package",
            "attributes": ["Infuse"],
        },
    )
    assert update == [{
        "Id": 44,
        "Name": "Infuse Brownies v2",
        "Description": "Updated process",
        "CategoryName": "Infused Edibles",
        "ProcessingSteps": "Mix, bake, cool, package",
        "Attributes": ["Infuse"],
    }]


def test_additive_template_payload_keeps_nested_active_ingredients_exact():
    body = build_facility_setup_payload(
        "additive_template_create",
        {
            "name": "Flower Feed Week 4",
            "additive_type": "Fertilizer",
            "application_device": "Injector",
            "epa_registration_number": "EPA-123",
            "product_supplier": "Example Supplier",
            "product_trade_name": "Example Feed",
            "note": "Use per SOP",
            "restrictive_entry_interval_quantity_description": "1",
            "restrictive_entry_interval_time_description": "day",
            "active_ingredients": [
                {"name": "Ingredient A", "percentage": "1.25", "unexpected": "drop"},
                {"name": "Ingredient B", "percentage": 2},
            ],
            "unexpected": "drop",
        },
    )
    assert body == [{
        "Name": "Flower Feed Week 4",
        "AdditiveType": "Fertilizer",
        "ApplicationDevice": "Injector",
        "EpaRegistrationNumber": "EPA-123",
        "Note": "Use per SOP",
        "ProductSupplier": "Example Supplier",
        "ProductTradeName": "Example Feed",
        "RestrictiveEntryIntervalQuantityDescription": "1",
        "RestrictiveEntryIntervalTimeDescription": "day",
        "ActiveIngredients": [
            {"Name": "Ingredient A", "Percentage": 1.25},
            {"Name": "Ingredient B", "Percentage": 2.0},
        ],
    }]


def test_additive_template_rejects_malformed_active_ingredients():
    with pytest.raises(ValueError, match="percentage is required"):
        build_facility_setup_payload(
            "additive_template_create",
            {
                "name": "Feed",
                "additive_type": "Fertilizer",
                "application_device": "Injector",
                "active_ingredients": [{"name": "Ingredient A"}],
            },
        )


def test_driver_and_vehicle_payloads_are_small_fixed_contracts():
    driver = build_facility_setup_payload(
        "driver_create",
        {
            "name": "Joe Smith",
            "drivers_license_number": "S1234567",
            "employee_id": "BTS000007",
            "phone": "must not pass through",
        },
    )
    assert driver == [{
        "Name": "Joe Smith",
        "DriversLicenseNumber": "S1234567",
        "EmployeeId": "BTS000007",
    }]

    vehicle = build_facility_setup_payload(
        "vehicle_update",
        {
            "id": "12",
            "make": "Toyota",
            "model": "Supra",
            "license_plate_number": "ABC1234",
            "registration_number": "REG-9",
            "year": 2026,
        },
    )
    assert vehicle == [{
        "Id": 12,
        "Make": "Toyota",
        "Model": "Supra",
        "LicensePlateNumber": "ABC1234",
        "RegistrationNumber": "REG-9",
    }]


@pytest.mark.parametrize(
    ("operation_type", "label"),
    [
        ("location_discontinue", "Location"),
        ("sublocation_discontinue", "Sublocation"),
        ("strain_discontinue", "Strain"),
        ("item_discontinue", "Item"),
        ("brand_discontinue", "Brand"),
        ("processing_job_type_discontinue", "Processing Job Type"),
        ("driver_discontinue", "Driver"),
        ("vehicle_discontinue", "Vehicle"),
    ],
)
def test_delete_previews_require_provider_id_and_never_create_a_body(operation_type: str, label: str):
    assert build_facility_setup_payload(operation_type, {"id": 1}) is None
    with pytest.raises(ValueError, match=rf"{label} ID is required"):
        build_facility_setup_payload(operation_type, {})


def test_unknown_action_never_guesses_a_payload():
    assert get_facility_setup_action("not-real") is None
    assert build_facility_setup_payload("not-real", {"anything": "value"}) is None
