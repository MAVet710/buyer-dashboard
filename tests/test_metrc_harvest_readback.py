from backend.app.services.metrc_harvest_readback import verify_harvest_state, verify_plant_harvested


def _readback(provider_id: str, source: dict):
    return {"ok": True, "http_status": 200, "records": [{"provider_id": provider_id, "source": {"Id": int(provider_id), **source}}]}


def test_harvest_state_requires_business_fields_not_id_alone():
    good = verify_harvest_state(
        readback=_readback("71", {"Name": "HARV-001", "DryingLocationName": "DRY-A", "CurrentWeight": 250.0}),
        provider_id="71",
        expected_name="HARV-001",
        expected_location="DRY-A",
        expected_weight_g=250.0,
    )
    assert good["matched"] is True

    wrong = verify_harvest_state(
        readback=_readback("71", {"Name": "HARV-001", "DryingLocationName": "DRY-B", "CurrentWeight": 249.0}),
        provider_id="71",
        expected_name="HARV-001",
        expected_location="DRY-A",
        expected_weight_g=250.0,
    )
    assert wrong["matched"] is False
    assert {row["field"] for row in wrong["differences"]} == {"DryingLocation", "CurrentWeight"}


def test_source_plant_requires_exact_harvest_evidence_or_absence():
    assigned = verify_plant_harvested(
        readback=_readback("91", {"HarvestId": 71, "HarvestName": "HARV-001", "GrowthPhase": "Harvested"}),
        plant_provider_id="91",
        harvest_provider_id="71",
        harvest_name="HARV-001",
    )
    assert assigned["matched"] is True

    absent = verify_plant_harvested(
        readback={"ok": False, "http_status": 404, "records": []},
        plant_provider_id="91",
        harvest_provider_id="71",
        harvest_name="HARV-001",
    )
    assert absent["matched"] is True

    wrong = verify_plant_harvested(
        readback=_readback("91", {"GrowthPhase": "Flowering", "LocationName": "FLOWER-A"}),
        plant_provider_id="91",
        harvest_provider_id="71",
        harvest_name="HARV-001",
    )
    assert wrong["matched"] is False
