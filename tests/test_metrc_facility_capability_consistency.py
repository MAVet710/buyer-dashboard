from __future__ import annotations

from pathlib import Path

from services.metrc_facility_capabilities import provider_boolean_capabilities, provider_capability


ROOT = Path(__file__).resolve().parents[1]
CAPABILITY = "CanCreateImmaturePlantPackagesFromPlants"


def test_capability_parser_accepts_facility_type_shape() -> None:
    record = {"LicenseNumber": "MA-1", "FacilityType": {CAPABILITY: False, "CanGrowPlants": True}}

    assert provider_capability(record, CAPABILITY) is False
    assert provider_boolean_capabilities(record)["CanGrowPlants"] is True


def test_capability_parser_accepts_top_level_shape() -> None:
    record = {"LicenseNumber": "MA-1", CAPABILITY: True}

    assert provider_capability(record, CAPABILITY) is True


def test_capability_parser_accepts_source_wrapped_shape() -> None:
    record = {"source": {"LicenseNumber": "MA-1", "FacilityType": {CAPABILITY: False}}}

    assert provider_capability(record, CAPABILITY) is False


def test_resume_diagnostics_share_canonical_capability_parser_and_v2_rows() -> None:
    summary = (ROOT / "backend/app/services/metrc_resume_diagnostics.py").read_text(encoding="utf-8")
    detail = (ROOT / "backend/app/services/metrc_resume_live_detail.py").read_text(encoding="utf-8")

    assert "provider_capability(facility" in summary
    assert "provider_capability(provider_facility" in detail
    assert "facility_rows = _rows(facilities_payload)" in detail
    assert 'facility_type.get("CanCreateImmaturePlantPackagesFromPlants")' not in summary
    assert 'facility_type.get("CanCreateImmaturePlantPackagesFromPlants")' not in detail
