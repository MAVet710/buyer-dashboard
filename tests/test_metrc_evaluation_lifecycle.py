from __future__ import annotations

import json

import pytest

from services.metrc_evaluation_lifecycle import (
    LIFECYCLE_EVALUATION_ACTIONS,
    MetrcLifecycleEvaluationError,
    build_lifecycle_evaluation_payload,
    execute_lifecycle_evaluation_action,
)


EXPECTED_ENDPOINTS = {
    "plant_batch_plantings": ("POST", "plantbatches/v2/plantings"),
    "plant_batch_packages": ("POST", "plantbatches/v2/packages"),
    "plant_batch_growthphase": ("POST", "plantbatches/v2/growthphase"),
    "plant_batch_delete": ("DELETE", "plantbatches/v2/"),
    "plant_location": ("PUT", "plants/v2/location"),
    "plant_plantings": ("POST", "plants/v2/plantings"),
    "plant_plantbatch_packages": ("POST", "plants/v2/plantbatch/packages"),
    "plant_delete": ("DELETE", "plants/v2/"),
    "plant_manicure": ("POST", "plants/v2/manicure"),
    "plant_harvest": ("PUT", "plants/v2/harvest"),
    "harvest_packages": ("POST", "harvests/v2/packages"),
    "harvest_waste": ("POST", "harvests/v2/waste"),
    "harvest_finish": ("PUT", "harvests/v2/finish"),
    "harvest_unfinish": ("PUT", "harvests/v2/unfinish"),
    "package_create": ("POST", "packages/v2/"),
    "package_item": ("PUT", "packages/v2/item"),
    "package_adjust": ("PUT", "packages/v2/adjust"),
    "package_finish": ("PUT", "packages/v2/finish"),
    "package_unfinish": ("PUT", "packages/v2/unfinish"),
}


def test_workbook_lifecycle_surface_has_exact_method_path_pairs():
    assert set(LIFECYCLE_EVALUATION_ACTIONS) == set(EXPECTED_ENDPOINTS)
    for operation, pair in EXPECTED_ENDPOINTS.items():
        spec = LIFECYCLE_EVALUATION_ACTIONS[operation]
        assert (spec.method, spec.path) == pair


def test_unknown_operation_cannot_supply_an_arbitrary_path():
    with pytest.raises(MetrcLifecycleEvaluationError, match="not enabled"):
        build_lifecycle_evaluation_payload(
            "arbitrary_write",
            {"method": "POST", "path": "sales/v2/receipts", "secret": "nope"},
        )


def test_plant_batch_planting_is_bounded_and_drops_unknown_keys():
    body = build_lifecycle_evaluation_payload(
        "plant_batch_plantings",
        {
            "name": "DL-EVAL-BATCH",
            "type": "Clone",
            "count": 5,
            "strain": "DL-EVAL-GMO",
            "location": "DL-EVAL-VEG",
            "sublocation": "Rack 1",
            "source_plant_batches": "SOURCE-A",
            "actual_date": "2026-09-03",
            "unexpected": "must-not-forward",
        },
    )
    assert body == [{
        "Name": "DL-EVAL-BATCH",
        "Type": "Clone",
        "Count": 5,
        "Strain": "DL-EVAL-GMO",
        "ActualDate": "2026-09-03",
        "Location": "DL-EVAL-VEG",
        "Sublocation": "Rack 1",
        "SourcePlantBatches": "SOURCE-A",
    }]
    assert "unexpected" not in json.dumps(body)


def test_growthphase_uses_current_v2_new_sublocation_field():
    body = build_lifecycle_evaluation_payload(
        "plant_batch_growthphase",
        {
            "name": "DL-EVAL-BATCH",
            "count": 2,
            "starting_tag": "1A4TEST000000000001",
            "growth_phase": "Vegetative",
            "new_location": "VEG-A",
            "new_sublocation": "Rack 2",
            "growth_date": "2026-09-03",
        },
    )
    assert body[0]["NewSublocation"] == "Rack 2"
    assert body[0]["StartingTag"] == "1A4TEST000000000001"


def test_manicure_preserves_plant_count_and_harvest_identity():
    body = build_lifecycle_evaluation_payload(
        "plant_manicure",
        {
            "plant": "1A4TESTPLANT1",
            "plant_count": 1,
            "weight": 12.5,
            "unit_of_weight": "Grams",
            "drying_location": "DRY-A",
            "drying_sublocation": "Bay 1",
            "harvest_name": "DL-EVAL-MANICURE",
            "actual_date": "2026-09-03",
        },
    )
    assert body[0]["PlantCount"] == 1
    assert body[0]["HarvestName"] == "DL-EVAL-MANICURE"
    assert body[0]["DryingSublocation"] == "Bay 1"


def test_harvest_package_uses_string_remediation_steps_and_current_fields():
    body = build_lifecycle_evaluation_payload(
        "harvest_packages",
        {
            "tag": "1A4TESTPACKAGE1",
            "item": "DL-EVAL-FLOWER",
            "actual_date": "2026-09-03",
            "location": "PKG-A",
            "product_requires_remediation": True,
            "remediate_product": True,
            "remediation_method_id": 7,
            "remediation_date": "2026-09-03",
            "remediation_steps": "Dry sift remediation",
            "product_requires_decontamination": True,
            "decontaminate_product": True,
            "decontamination_date": "2026-09-03",
            "decontamination_steps": "Validated decontamination",
            "ingredients": [
                {"harvest_id": 41, "harvest_name": "DL-EVAL-HARVEST", "weight": 50.5, "unit_of_weight": "Grams"}
            ],
        },
    )
    row = body[0]
    assert row["RemediationSteps"] == "Dry sift remediation"
    assert isinstance(row["RemediationSteps"], str)
    assert row["ProductRequiresDecontamination"] is True
    assert row["DecontaminationSteps"] == "Validated decontamination"
    assert row["Ingredients"] == [{
        "Weight": 50.5,
        "UnitOfWeight": "Grams",
        "HarvestId": 41,
        "HarvestName": "DL-EVAL-HARVEST",
    }]


def test_package_create_uses_source_package_ingredients_and_decimal_quantity():
    body = build_lifecycle_evaluation_payload(
        "package_create",
        {
            "tag": "1A4TESTPACKAGE2",
            "item": "DL-EVAL-BULK",
            "quantity": 25.25,
            "unit_of_measure": "Grams",
            "actual_date": "2026-09-03",
            "ingredients": [{"package": "1A4SOURCE1", "quantity": 25.25, "unit_of_measure": "Grams"}],
        },
    )
    assert body[0]["Quantity"] == 25.25
    assert body[0]["Ingredients"] == [{"Package": "1A4SOURCE1", "Quantity": 25.25, "UnitOfMeasure": "Grams"}]


def test_package_update_context_id_is_never_forwarded_to_metrc():
    body = build_lifecycle_evaluation_payload(
        "package_item",
        {"package_id": 88, "label": "1A4PKG", "item": "DL-EVAL-NEW-ITEM"},
    )
    assert body == [{"Label": "1A4PKG", "Item": "DL-EVAL-NEW-ITEM"}]
    assert "package_id" not in json.dumps(body)


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"" if payload is None else b"json"
        self.text = "" if payload is None else json.dumps(payload)

    def json(self):
        return self._payload


def _matching_readback(provider_id: str):
    def readback(**kwargs):
        assert kwargs["path_parameters"] == {"id": provider_id}
        return {
            "ok": True,
            "http_status": 200,
            "records": [{
                "provider_id": provider_id,
                "last_modified": "2026-09-03T21:00:00Z",
                "source": {"Id": int(provider_id)},
            }],
        }
    return readback


def test_response_identity_write_requires_http_200_and_exact_readback():
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, {"Ids": [321]})

    evidence = execute_lifecycle_evaluation_action(
        operation_type="plant_batch_plantings",
        payload={
            "name": "DL-EVAL-BATCH",
            "type": "Clone",
            "count": 2,
            "strain": "DL-EVAL-GMO",
            "actual_date": "2026-09-03",
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-key-runtime-only",
        user_api_key="user-key-runtime-only",
        request_fn=request,
        readback_fn=_matching_readback("321"),
    )

    assert evidence["passed"] is True
    assert evidence["stage"] == "complete"
    assert evidence["provider_id"] == "321"
    assert evidence["last_modified"] == "2026-09-03T21:00:00Z"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://sandbox-api-ma.metrc.com/plantbatches/v2/plantings"
    serialized = json.dumps(evidence)
    assert "vendor-key-runtime-only" not in serialized
    assert "user-key-runtime-only" not in serialized


def test_input_identity_package_mutation_reads_back_exact_package():
    captured = {}

    def request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return FakeResponse(200)

    evidence = execute_lifecycle_evaluation_action(
        operation_type="package_adjust",
        payload={
            "package_id": 72,
            "label": "1A4PKG",
            "quantity": -1.5,
            "unit_of_measure": "Grams",
            "adjustment_reason": "Drying",
            "adjustment_date": "2026-09-03",
            "reason_note": "Evaluation adjustment",
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime",
        user_api_key="user-runtime",
        request_fn=request,
        readback_fn=_matching_readback("72"),
    )
    assert evidence["passed"] is True
    assert evidence["provider_id"] == "72"
    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/packages/v2/adjust")
    assert captured["json"][0]["Quantity"] == -1.5


def test_delete_can_be_verified_by_exact_not_found_readback():
    def request(*args, **kwargs):
        return FakeResponse(200)

    def absent(**kwargs):
        assert kwargs["path_parameters"] == {"id": "91"}
        return {"ok": False, "http_status": 404, "records": [], "message": "Not found"}

    evidence = execute_lifecycle_evaluation_action(
        operation_type="plant_delete",
        payload={
            "id": 91,
            "count": 1,
            "actual_date": "2026-09-03",
            "reason_note": "Evaluation destroy",
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime",
        user_api_key="user-runtime",
        request_fn=request,
        readback_fn=absent,
    )
    assert evidence["passed"] is True
    assert evidence["provider_id"] == "91"


def test_http_201_is_not_misrepresented_as_proficiency_pass():
    def request(*args, **kwargs):
        return FakeResponse(201, {"Ids": [44]})

    evidence = execute_lifecycle_evaluation_action(
        operation_type="plant_batch_plantings",
        payload={"name": "DL", "type": "Clone", "count": 1, "strain": "GMO", "actual_date": "2026-09-03"},
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime",
        user_api_key="user-runtime",
        request_fn=request,
        readback_fn=lambda **kwargs: pytest.fail("readback must not run after non-200"),
    )
    assert evidence["passed"] is False
    assert evidence["stage"] == "write"
    assert evidence["http_status"] == 201


def test_write_without_response_identity_does_not_fake_a_pass():
    def request(*args, **kwargs):
        return FakeResponse(200, {})

    evidence = execute_lifecycle_evaluation_action(
        operation_type="harvest_packages",
        payload={
            "tag": "1A4PKG",
            "item": "FLOWER",
            "actual_date": "2026-09-03",
            "ingredients": [{"harvest_id": 10, "weight": 10, "unit_of_weight": "Grams"}],
        },
        license_number="TEST-LICENSE",
        integrator_api_key="vendor-runtime",
        user_api_key="user-runtime",
        request_fn=request,
        readback_fn=lambda **kwargs: pytest.fail("readback must not run without provider identity"),
    )
    assert evidence["passed"] is False
    assert evidence["stage"] == "readback_identity"


def test_production_execution_is_blocked_before_network_dispatch():
    with pytest.raises(MetrcLifecycleEvaluationError, match="restricted to the Metrc sandbox"):
        execute_lifecycle_evaluation_action(
            operation_type="harvest_unfinish",
            payload={"id": 1},
            license_number="TEST-LICENSE",
            integrator_api_key="vendor-runtime",
            user_api_key="user-runtime",
            environment="production",
            request_fn=lambda *args, **kwargs: pytest.fail("network dispatch must remain blocked"),
        )


def test_duplicate_credential_roles_fail_closed():
    with pytest.raises(MetrcLifecycleEvaluationError, match="must be distinct"):
        execute_lifecycle_evaluation_action(
            operation_type="harvest_unfinish",
            payload={"id": 1},
            license_number="TEST-LICENSE",
            integrator_api_key="same-runtime-key",
            user_api_key="same-runtime-key",
            request_fn=lambda *args, **kwargs: pytest.fail("network dispatch must remain blocked"),
        )
