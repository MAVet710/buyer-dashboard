import pytest
from services.metrc_resume_response import (
    ResumeResponseError, collection_values, numeric, object_rows, package_record,
    reference_names, total_pages, validate_sandbox_url, verify_package,
)


def test_string_references_are_not_silently_removed():
    assert reference_names(["Consumer", "Patient"]) == ["Consumer", "Patient"]
    assert reference_names(["Package", "Plant"]) == ["Package", "Plant"]
    assert reference_names({"Data": [{"Name": "Package"}]}) == ["Package"]


@pytest.mark.parametrize("payload", [{"error": "unavailable"}, None, "not JSON", [False]])
def test_unknown_response_is_not_reported_as_empty(payload):
    with pytest.raises(ResumeResponseError):
        reference_names(payload)


def test_objects_remain_distinct_from_reference_lists():
    assert object_rows({"Data": [{"Id": 1}], "TotalPages": 1}) == [{"Id": 1}]
    with pytest.raises(ResumeResponseError):
        object_rows(["Consumer"])
    assert collection_values([]) == []


def test_v2_top_level_pagination():
    assert total_pages({"Data": [{"Id": 1}], "TotalPages": 3}) == 3
    assert total_pages({"Data": [], "TotalPages": 0}) == 1
    assert total_pages({"Data": [], "Meta": {"TotalPages": 2}}) == 2
    assert total_pages([]) == 1


@pytest.mark.parametrize("payload", [
    {"Data": []}, {"Data": [], "TotalPages": "bogus"},
    {"Data": [], "TotalPages": True}, {"Data": [], "TotalPages": -1},
    {"Data": [], "TotalPages": 1001},
    {"Data": [], "TotalPages": 2, "Meta": {"TotalPages": 1}},
    {"Data": [{"Id": 1}], "TotalPages": 0},
])
def test_pagination_fails_closed(payload):
    with pytest.raises(ResumeResponseError):
        total_pages(payload)


@pytest.mark.parametrize("url", [
    "https://api-ma.metrc.com", "http://sandbox-api-ma.metrc.com",
    "https://sandbox-api-ma.metrc.com.invalid", "https://user@sandbox-api-ma.metrc.com",
    "https://sandbox-api-ma.metrc.com/path", "https://sandbox-api-ma.metrc.com?mode=prod",
])
def test_only_exact_sandbox_origin_allowed(url):
    with pytest.raises(ResumeResponseError):
        validate_sandbox_url(url)


def test_sandbox_origin():
    assert validate_sandbox_url("https://sandbox-api-ma.metrc.com/") == "https://sandbox-api-ma.metrc.com"


def package():
    return {"Id": 20, "Label": "TEST-LABEL", "Item": {"Name": "Test Clones"},
            "Quantity": 1, "UnitOfMeasureName": "Each", "IsFinished": False, "IsOnHold": False}


def verify(row):
    verify_package(row, label="TEST-LABEL", item_name="Test Clones", quantity=1, unit="Each", provider_id=20)


def test_correct_postconditions():
    verify(package())
    assert package_record(package(), "TEST-LABEL")["Id"] == 20


@pytest.mark.parametrize("field,value", [
    ("Id", 21), ("Label", "OTHER"), ("Item", {"Name": "Wrong Item"}),
    ("Quantity", 0), ("Quantity", float("nan")), ("Quantity", True),
    ("UnitOfMeasureName", "Grams"), ("IsFinished", True), ("IsOnHold", None),
])
def test_id_only_readback_cannot_pass(field, value):
    row = package()
    row[field] = value
    with pytest.raises(ResumeResponseError):
        verify(row)


def test_zero_quantity_is_preserved():
    assert numeric(0) == 0
    with pytest.raises(ResumeResponseError):
        package_record(package(), "WRONG-LABEL")
