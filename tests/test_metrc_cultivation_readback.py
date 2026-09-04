from __future__ import annotations

from backend.app.services.metrc_cultivation_readback import (
    provider_ids_from_response,
    verify_plant_batch_creation,
    verify_plant_location,
    verify_vegetative_plants,
)


def test_provider_ids_from_response_is_recursive_and_stable():
    payload = {"Ids": [31, 32], "Data": [{"Id": 32}, {"Id": 33}]}
    assert provider_ids_from_response(payload) == ["31", "32", "33"]


def test_plant_batch_creation_requires_requested_business_state():
    result = verify_plant_batch_creation(
        provider_request_body=[{
            "Name": "DL-GMO-001",
            "Type": "Clone",
            "Count": 10,
            "Strain": "GMO",
            "Location": "VEG A",
            "ActualDate": "2026-09-04",
        }],
        provider_id="55",
        readback={
            "ok": True,
            "records": [{
                "provider_id": "55",
                "source": {
                    "Id": 55,
                    "Name": "DL-GMO-001",
                    "Type": "Clone",
                    "UntrackedCount": 10,
                    "StrainName": "GMO",
                    "LocationName": "VEG A",
                    "PlantedDate": "2026-09-04T00:00:00Z",
                },
            }],
        },
    )
    assert result["matched"] is True
    assert result["differences"] == []


def test_plant_batch_same_id_wrong_count_is_not_verified():
    result = verify_plant_batch_creation(
        provider_request_body=[{"Name": "DL-GMO-001", "Type": "Clone", "Count": 10, "Strain": "GMO", "ActualDate": "2026-09-04"}],
        provider_id="55",
        readback={"ok": True, "records": [{"provider_id": "55", "source": {"Id": 55, "Name": "DL-GMO-001", "Type": "Clone", "UntrackedCount": 9, "StrainName": "GMO", "PlantedDate": "2026-09-04"}}]},
    )
    assert result["matched"] is False
    assert any(row["field"] == "Count" for row in result["differences"])


def test_plant_location_requires_destination_not_only_same_id():
    result = verify_plant_location(
        provider_request_body=[{"Id": 9, "Label": "1A4PLANT1", "Location": "FLOWER B", "ActualDate": "2026-09-04"}],
        provider_id="9",
        readback={"ok": True, "records": [{"provider_id": "9", "source": {"Id": 9, "Label": "1A4PLANT1", "LocationName": "FLOWER A"}}]},
    )
    assert result["matched"] is False
    assert result["differences"][0]["field"] == "Location"


def test_vegetative_verification_requires_every_output_plant():
    readbacks = [
        {"ok": True, "records": [{"provider_id": "101", "label": "1A4TAG001", "source": {"Id": 101, "Label": "1A4TAG001", "GrowthPhase": "Vegetative", "LocationName": "VEG A", "StrainName": "GMO"}}]},
        {"ok": True, "records": [{"provider_id": "102", "label": "1A4TAG002", "source": {"Id": 102, "Label": "1A4TAG002", "GrowthPhase": "Vegetative", "LocationName": "VEG A", "StrainName": "GMO"}}]},
    ]
    result = verify_vegetative_plants(readbacks=readbacks, expected_count=2, expected_location="VEG A", expected_strain="GMO")
    assert result["matched"] is True
    assert [row["provider_id"] for row in result["plants"]] == ["101", "102"]


def test_vegetative_verification_rejects_partial_or_wrong_location():
    result = verify_vegetative_plants(
        readbacks=[{"ok": True, "records": [{"provider_id": "101", "label": "1A4TAG001", "source": {"Id": 101, "Label": "1A4TAG001", "GrowthPhase": "Vegetative", "LocationName": "WRONG", "StrainName": "GMO"}}]}],
        expected_count=2,
        expected_location="VEG A",
        expected_strain="GMO",
    )
    assert result["matched"] is False
    fields = {row["field"] for row in result["differences"]}
    assert "Count" in fields
    assert "Location" in fields
