from __future__ import annotations

import json

import pytest

from services.metrc_evaluation_workbook_contract import (
    MetrcWorkbookContractError,
    execute_two_plant_harvest_evaluation_action,
    facility_supports_family,
    required_families,
    resolve_permission_family,
    validate_facility_family,
    validate_workbook_payload,
    verify_workbook_evidence,
)


def _facility(license_number: str, **capabilities):
    return {
        "provider_id": license_number,
        "source": {
            "LicenseNumber": license_number,
            "FacilityType": capabilities,
        },
    }


def test_permission_families_follow_workbook_required_dependency_prose() -> None:
    assert set(required_families("strain_create")) == {"grow", "processor", "labs", "sales"}
    assert set(required_families("item_update")) == {"grow", "processor", "sales"}
    assert set(required_families("package_create")) == {"grow", "processor", "labs", "sales"}
    assert required_families("lab_test_record") == ("labs",)
    assert required_families("sales_delivery_create") == ("sales",)
    assert required_families("plant_harvest") == ("grow",)
    assert required_families("transfer_template_create") == ()


def test_shared_permission_sections_require_explicit_family() -> None:
    with pytest.raises(MetrcWorkbookContractError, match="multiple facility families"):
        resolve_permission_family("package_create")
    assert resolve_permission_family("package_create", "labs") == "labs"
    assert resolve_permission_family("sales_delivery_create") == "sales"
    with pytest.raises(MetrcWorkbookContractError, match="optional Transfer Template"):
        resolve_permission_family("transfer_template_create")


def test_facility_family_matching_is_explicit_not_license_number_guessing() -> None:
    grow = _facility("GROW", CanGrowPlants=True, CanTrackVegetativePlants=True)
    processor = _facility("PROC", CanInfuseProducts=True)
    lab = _facility("LAB", CanTestPackages=True)
    sales = _facility("SALE", CanSellToConsumers=True, CanDeliverSalesToConsumers=True)
    assert facility_supports_family(grow, "grow") is True
    assert facility_supports_family(processor, "processor") is True
    assert facility_supports_family(lab, "labs") is True
    assert facility_supports_family(sales, "sales") is True
    assert facility_supports_family(grow, "sales") is False

    verified = validate_facility_family(
        operation_type="lab_test_record",
        permission_family="labs",
        license_number="LAB",
        facility_records=[grow, processor, lab, sales],
    )
    assert verified["permission_family"] == "labs"
    assert verified["license_number"] == "LAB"

    with pytest.raises(MetrcWorkbookContractError, match="does not expose"):
        validate_facility_family(
            operation_type="lab_test_record",
            permission_family="labs",
            license_number="GROW",
            facility_records=[grow, lab],
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


def test_task20_requires_exactly_two_distinct_plants_and_shared_harvest_context() -> None:
    validate_workbook_payload("plant_harvest", _two_plants())
    one = _two_plants()
    one["plants"] = one["plants"][:1]
    with pytest.raises(MetrcWorkbookContractError, match="exactly the 2 remaining plants"):
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
