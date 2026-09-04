from backend.app.services.metrc_package_readback import package_snapshot, verify_package_state


def readback(source: dict, *, provider_id="77"):
    return {
        "ok": True,
        "records": [{
            "provider_id": provider_id,
            "label": source.get("Label", "1A4000000000000000000001"),
            "quantity": source.get("Quantity"),
            "unit_of_measure": source.get("UnitOfMeasureName", "Grams"),
            "last_modified": "2026-09-04T10:00:00Z",
            "source": source,
        }],
    }


def test_package_readback_verifies_identity_item_quantity_unit_and_finished_state():
    result = verify_package_state(
        readback=readback({
            "Id": 77,
            "Label": "1A4000000000000000000001",
            "Item": {"Name": "GMO Flower"},
            "Quantity": 100.0,
            "UnitOfMeasureName": "Grams",
            "LocationName": "Finished Goods",
            "IsFinished": False,
        }),
        provider_id="77",
        expected_label="1A4000000000000000000001",
        expected_item="GMO Flower",
        expected_quantity=100,
        expected_unit="grams",
        expected_finished=False,
        expected_location="Finished Goods",
    )
    assert result["matched"] is True
    assert result["differences"] == []


def test_same_package_id_with_wrong_quantity_fails_closed():
    result = verify_package_state(
        readback=readback({"Id": 77, "Label": "TAG", "ItemName": "GMO", "Quantity": 90, "UnitOfMeasureName": "Grams", "IsFinished": False}),
        provider_id="77",
        expected_quantity=100,
        expected_unit="Grams",
    )
    assert result["matched"] is False
    assert result["differences"] == [{"field": "quantity", "expected": 100.0, "actual": 90.0}]


def test_item_and_nested_aliases_are_supported_but_missing_item_is_not_accepted():
    good = verify_package_state(
        readback=readback({"Id": 77, "Label": "TAG", "Item": {"Name": "GMO"}, "Quantity": 1, "UnitOfMeasureAbbreviation": "g"}),
        provider_id="77",
        expected_item="gmo",
    )
    assert good["matched"] is True
    bad = verify_package_state(
        readback=readback({"Id": 77, "Label": "TAG", "Quantity": 1, "UnitOfMeasureName": "Grams"}),
        provider_id="77",
        expected_item="GMO",
    )
    assert bad["matched"] is False


def test_finished_date_can_prove_finish_and_empty_finished_date_can_prove_unfinish():
    finished = package_snapshot(readback({"Id": 77, "Label": "TAG", "FinishedDate": "2026-09-04"}))
    active = package_snapshot(readback({"Id": 77, "Label": "TAG", "FinishedDate": None}))
    assert finished["finished"] is True
    assert active["finished"] is False


def test_unknown_finished_state_does_not_verify_finish():
    result = verify_package_state(
        readback=readback({"Id": 77, "Label": "TAG"}),
        provider_id="77",
        expected_finished=True,
    )
    assert result["matched"] is False
    assert result["differences"][0]["field"] == "finished"


def test_readback_must_return_exactly_one_provider_package():
    result = verify_package_state(readback={"ok": True, "records": []}, provider_id="77")
    assert result["matched"] is False
    assert result["differences"][0]["field"] == "readback"
