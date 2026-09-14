from __future__ import annotations

import json

import pytest

from services.metrc_evaluation_workbook_contract import (
    MetrcWorkbookContractError,
    WORKBOOK_OPTIONAL_DEPENDENCIES,
    WORKBOOK_PERMISSION_DEPENDENCIES,
    execute_two_plant_harvest_evaluation_action,
    select_facility_for_operation,
    validate_workbook_payload,
    verify_workbook_evidence,
)


def _facility(name: str, license_number: str, **capabilities):
    return {
        "provider_id": license_number,
        "source": {
            "Name": name,
            "LicenseNumber": license_number,
            "FacilityType": capabilities,
        },
    }


def _facilities():
    return [
        _facility(
            "Sandbox Marijuana Cultivator",
            "GROW",
            CanGrowPlants=True,
            CanTrackVegetativePlants=True,
            CanCreateDerivedPackages=True,
        ),
        _facility(
            "Sandbox Independent Testing Laboratory",
            "LAB",
            CanTestPackages=True,
            CanCreateDerivedPackages=True,
        ),
        _facility(
            "Sandbox Marijuana Retailer",
            "SALE",
            IsRetail=True,
            CanSellToConsumers=True,
            CanDeliverSalesToConsumers=True,
            CanCreateDerivedPackages=True,
        ),
    ]


def test_permission_dependency_table_is_informational_not_extra_task_count() -> None:
    assert "Strains" in WORKBOOK_PERMISSION_DEPENDENCIES["grow"]
    assert "Strains" in WORKBOOK_PERMISSION_DEPENDENCIES["labs"]
    assert "Sales Deliveries" in WORKBOOK_PERMISSION_DEPENDENCIES["sales"]
    assert WORKBOOK_OPTIONAL_DEPENDENCIES["labs"] == ("Items", "Transfer Templates")


def test_runner_selects_dedicated_facility_per_operation_instead_of_one_global_license() -> None:
    rows = _facilities()
    assert select_facility_for_operation(operation_type="plant_batch_plantings", facility_records=rows)["license_number"] == "GROW"
    assert select_facility_for_operation(operation_type="lab_test_record", facility_records=rows)["license_number"] == "LAB"
    assert select_facility_for_operation(operation_type="sales_delivery_create", facility_records=rows)["license_number"] == "SALE"


def test_explicit_license_is_validated_against_operation_capability() -> None:
    rows = _facilities()
    selected = select_facility_for_operation(
        operation_type="lab_test_record",
        facility_records=rows,
        explicit_license="LAB",
    )
    assert selected["selection"] == "explicit"

    with pytest.raises(MetrcWorkbookContractError, match="capability profile"):
        select_facility_for_operation(
            operation_type="lab_test_record",
            facility_records=rows,
            explicit_license="GROW",
        )


def test_literal_plant_batch_counts_are_enforced_before_provider_dispatch() -> None:
    validate_workbook_payload("plant_batch_plantings", {"count": 6})
    validate_workbook_payload("plant_batch_packages", {"count": 3})
    validate_workbook_payload("plant_batch_growthphase", {"count": 2, "growth_phase": "Vegetative"})
    validate_workbook_payload("plant_batch_delete", {"count": 1})
    validate_workbook_payload("plant_delete", {"count": 1})

    with pytest.raises(MetrcWorkbookContractError, match="6 plants"):
        validate_workbook_payload("plant_batch_plantings", {"count": 5})
    with pytest.raises(MetrcWorkbookContractError, match="3 clones"):
        validate_workbook_payload("plant_batch_packages", {"count": 2})
    with pytest.raises(MetrcWorkbookContractError, match="Vegetative"):
        validate_workbook_payload("plant_batch_growthphase", {"count": 2, "growth_phase": "Flowering"})


def _two_plants():
    return {
        "harvest_name": "DL-EVAL-HARVEST",
        "actual_date": "2026-09-14",
        "drying_location": "Dry Room",
        "unit_of_weight": "Grams",
        "plants": [
            {"id": 91, "plant": "PLANT-91", "weight": 10},
            {"id": 92, "plant": "PLANT-92", "weight": 12},
        ],
    }


def test_task20_requires_two_distinct_plants_and_shared_harvest_context() -> None:
    validate_workbook_payload("plant_harvest", _two_plants())
    one = _two_plants()
    one["plants"] = one["plants"][:1]
    with pytest.raises(MetrcWorkbookContractError, match="2 remaining plants"):
        validate_workbook_payload("plant_harvest", one)


def test_harvest_waste_rejects_moisture_loss() -> None:
    with pytest.raises(MetrcWorkbookContractError, match="moisture loss"):
        validate_workbook_payload("harvest_waste", {"waste_type": "Moisture Loss"})
    validate_workbook_payload("harvest_waste", {"waste_type": "Plant Material"})


def test_package_adjust_must_declare_zero_final_quantity() -> None:
    validate_workbook_payload("package_adjust", {"expected_final_quantity": 0})
    with pytest.raises(MetrcWorkbookContractError, match="expected_final_quantity=0"):
        validate_workbook_payload("package_adjust", {"expected_final_quantity": 1})


def _tx(label: str):
    return {"package_label": label, "quantity": 1, "unit_of_measure": "Each", "total_amount": 10}


def test_sales_delivery_sequence_matches_workbook_3_then_2_then_accepted_returned() -> None:
    validate_workbook_payload(
        "sales_delivery_create",
        {"sales_customer_type": "Consumer", "transactions": [_tx("A"), _tx("B"), _tx("C")]},
    )
    validate_workbook_payload(
        "sales_delivery_update",
        {"sales_customer_type": "Consumer", "transactions": [_tx("A"), _tx("B")]},
    )
    validate_workbook_payload(
        "sales_delivery_complete",
        {"accepted_packages": ["A"], "returned_packages": [{"label": "B"}]},
    )

    with pytest.raises(MetrcWorkbookContractError, match="exactly 3"):
        validate_workbook_payload(
            "sales_delivery_create",
            {"sales_customer_type": "Consumer", "transactions": [_tx("A")]},
        )
    with pytest.raises(MetrcWorkbookContractError, match="exactly 2"):
        validate_workbook_payload(
            "sales_delivery_update",
            {"sales_customer_type": "Consumer", "transactions": [_tx("A")]},
        )
    with pytest.raises(MetrcWorkbookContractError, match="exactly 1 AcceptedPackage"):
        validate_workbook_payload(
            "sales_delivery_complete",
            {"accepted_packages": ["A", "B"], "returned_packages": [{"label": "C"}]},
        )


def _evidence(source):
    return {
        "passed": True,
        "stage": "complete",
        "http_status": 200,
        "readback": {"ok": True, "http_status": 200, "records": [{"provider_id": "1", "source": source}]},
    }


def test_http_200_update_is_not_a_pass_until_workbook_field_changed() -> None:
    failed = verify_workbook_evidence(
        "strain_update",
        {"indica_percentage": 60, "sativa_percentage": 40},
        _evidence({"Id": 1, "IndicaPercentage": 50, "SativaPercentage": 50}),
    )
    assert failed["passed"] is False
    assert failed["stage"] == "workbook_readback"

    passed = verify_workbook_evidence(
        "strain_update",
        {"indica_percentage": 60, "sativa_percentage": 40},
        _evidence({"Id": 1, "IndicaPercentage": 60, "SativaPercentage": 40}),
    )
    assert passed["passed"] is True
    assert passed["workbook_readback_verified"] is True


def test_package_adjust_readback_must_be_zero() -> None:
    payload = {"expected_final_quantity": 0}
    assert verify_workbook_evidence("package_adjust", payload, _evidence({"Id": 1, "Quantity": 0}))["passed"] is True
    assert verify_workbook_evidence("package_adjust", payload, _evidence({"Id": 1, "Quantity": 2}))["passed"] is False


class Response:
    status_code = 200
    content = b"json"
    text = '{"Ids":[71]}'
    def json(self):
        return {"Ids": [71]}


def test_task20_sends_two_rows_once_and_verifies_both_source_plants() -> None:
    captured = {}

    def request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return Response()

    def readback(**kwargs):
        resource = kwargs["resource"]
        provider_id = str(kwargs["path_parameters"]["id"])
        if resource == "harvests_by_id":
            return {
                "ok": True,
                "http_status": 200,
                "records": [{"provider_id": "71", "source": {"Id": 71, "Name": "DL-EVAL-HARVEST"}}],
            }
        assert resource == "plants_by_id"
        return {
            "ok": True,
            "http_status": 200,
            "records": [{
                "provider_id": provider_id,
                "source": {"Id": int(provider_id), "HarvestId": 71, "HarvestName": "DL-EVAL-HARVEST", "GrowthPhase": "Harvested"},
            }],
        }

    result = execute_two_plant_harvest_evaluation_action(
        payload=_two_plants(),
        license_number="GROW-LICENSE",
        integrator_api_key="vendor-fixture",
        user_api_key="user-fixture",
        request_fn=request,
        readback_fn=readback,
    )
    assert result["passed"] is True
    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/plants/v2/harvest")
    assert len(captured["json"]) == 2
    assert {row["Plant"] for row in captured["json"]} == {"PLANT-91", "PLANT-92"}
    assert all(row["HarvestName"] == "DL-EVAL-HARVEST" for row in captured["json"])
    assert len(result["plant_readback"]) == 2
    assert "vendor-fixture" not in json.dumps(result)
    assert "user-fixture" not in json.dumps(result)
