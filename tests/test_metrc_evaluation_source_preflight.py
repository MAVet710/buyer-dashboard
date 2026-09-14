from __future__ import annotations

import pytest

from services.metrc_evaluation_source_preflight import preflight_workbook_source_state
from services.metrc_evaluation_workbook_contract import MetrcWorkbookContractError


BASE = {
    "license_number": "TEST-LICENSE",
    "integrator_api_key": "vendor-fixture",
    "user_api_key": "user-fixture",
}


def _read(provider_id: str, source: dict):
    return {
        "ok": True,
        "http_status": 200,
        "records": [{"provider_id": str(provider_id), "source": {"Id": int(provider_id), **source}}],
    }


def test_plants_step1_requires_flowering_plant_and_different_location() -> None:
    def flowering(**kwargs):
        assert kwargs["resource"] == "plants_by_id"
        return _read("91", {"GrowthPhase": "Flowering", "LocationName": "Room A"})

    result = preflight_workbook_source_state(
        operation_type="plant_location",
        payload={"id": 91, "location": "Room B"},
        fetch_fn=flowering,
        **BASE,
    )
    assert result["verified"] is True
    assert result["growth_phase"] == "Flowering"

    with pytest.raises(MetrcWorkbookContractError, match="different location"):
        preflight_workbook_source_state(
            operation_type="plant_location",
            payload={"id": 91, "location": "Room A"},
            fetch_fn=flowering,
            **BASE,
        )

    def vegetative(**kwargs):
        return _read("91", {"GrowthPhase": "Vegetative", "LocationName": "Room A"})

    with pytest.raises(MetrcWorkbookContractError, match="Flowering Plant"):
        preflight_workbook_source_state(
            operation_type="plant_location",
            payload={"id": 91, "location": "Room B"},
            fetch_fn=vegetative,
            **BASE,
        )


def test_harvest_waste_must_equal_provider_remaining_weight() -> None:
    def read(**kwargs):
        assert kwargs["resource"] == "harvests_by_id"
        return _read("71", {"CurrentWeight": 12.5, "UnitOfWeightName": "Grams"})

    result = preflight_workbook_source_state(
        operation_type="harvest_waste",
        payload={"id": 71, "waste_weight": 12.5, "unit_of_weight": "Grams"},
        fetch_fn=read,
        **BASE,
    )
    assert result["remaining_weight"] == 12.5

    with pytest.raises(MetrcWorkbookContractError, match="remaining weight"):
        preflight_workbook_source_state(
            operation_type="harvest_waste",
            payload={"id": 71, "waste_weight": 10, "unit_of_weight": "Grams"},
            fetch_fn=read,
            **BASE,
        )


def test_package_adjust_delta_must_land_exactly_at_zero() -> None:
    def read(**kwargs):
        assert kwargs["resource"] == "packages_by_id"
        return _read("72", {"Quantity": 3, "UnitOfMeasureName": "Each", "IsFinished": False})

    result = preflight_workbook_source_state(
        operation_type="package_adjust",
        payload={"package_id": 72, "quantity": -3, "unit_of_measure": "Each"},
        fetch_fn=read,
        **BASE,
    )
    assert result["current_quantity"] == 3

    with pytest.raises(MetrcWorkbookContractError, match="adjust the package to 0"):
        preflight_workbook_source_state(
            operation_type="package_adjust",
            payload={"package_id": 72, "quantity": -1, "unit_of_measure": "Each"},
            fetch_fn=read,
            **BASE,
        )


def test_package_finish_requires_zero_and_unfinish_requires_finished() -> None:
    def zero_unfinished(**kwargs):
        return _read("72", {"Quantity": 0, "UnitOfMeasureName": "Each", "IsFinished": False})

    assert preflight_workbook_source_state(
        operation_type="package_finish",
        payload={"package_id": 72},
        fetch_fn=zero_unfinished,
        **BASE,
    )["verified"] is True

    with pytest.raises(MetrcWorkbookContractError, match="finished in Step 4"):
        preflight_workbook_source_state(
            operation_type="package_unfinish",
            payload={"package_id": 72},
            fetch_fn=zero_unfinished,
            **BASE,
        )

    def zero_finished(**kwargs):
        return _read("72", {"Quantity": 0, "UnitOfMeasureName": "Each", "IsFinished": True})

    assert preflight_workbook_source_state(
        operation_type="package_unfinish",
        payload={"package_id": 72},
        fetch_fn=zero_finished,
        **BASE,
    )["is_finished"] is True


def test_delivery_update_and_complete_preflight_same_provider_delivery_sequence() -> None:
    def three(**kwargs):
        return _read("55", {"Transactions": [{}, {}, {}]})

    assert preflight_workbook_source_state(
        operation_type="sales_delivery_update",
        payload={"id": 55},
        fetch_fn=three,
        **BASE,
    )["transaction_count"] == 3

    def two(**kwargs):
        return _read("55", {"Transactions": [{}, {}]})

    assert preflight_workbook_source_state(
        operation_type="sales_delivery_complete",
        payload={"id": 55},
        fetch_fn=two,
        **BASE,
    )["transaction_count"] == 2
