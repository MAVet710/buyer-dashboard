from __future__ import annotations

import pytest

from modules.regulatory.facility_setup_contracts import (
    build_facility_setup_payload,
    get_facility_setup_action,
    list_facility_setup_actions,
)


def test_facility_setup_catalog_exposes_master_data_without_enabling_dispatch():
    rows = {row.operation_type: row for row in list_facility_setup_actions()}
    assert "location_create" in rows
    assert "sublocation_create" in rows
    assert "strain_create" in rows
    assert "item_create" in rows
    assert "processing_job_type_create" in rows
    assert "additive_template_create" in rows
    assert "driver_create" in rows
    assert "vehicle_create" in rows
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
        {"name": "Flower Room 2", "location_type_name": "Default"},
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


@pytest.mark.parametrize(
    "operation_type",
    [
        "item_create",
        "brand_create",
        "processing_job_type_create",
        "additive_template_create",
        "driver_create",
        "vehicle_create",
    ],
)
def test_complex_actions_stay_catalogued_without_guessing_payload(operation_type: str):
    spec = get_facility_setup_action(operation_type)
    assert spec is not None
    assert spec.dispatch_enabled is False
    assert build_facility_setup_payload(operation_type, {"name": "Example", "unexpected": "do not forward"}) is None