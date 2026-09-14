from __future__ import annotations

from pathlib import Path

from backend.app.services.metrc_evaluation_rebaseline import (
    PAGED_RESOURCES,
    REFERENCE_RESOURCES,
    _candidate,
)


ROOT = Path(__file__).resolve().parents[1]


def test_rebaseline_covers_remaining_evaluation_prerequisite_reads() -> None:
    resources = {name for name, _path in (*PAGED_RESOURCES, *REFERENCE_RESOURCES)}
    assert {
        "locations",
        "strains",
        "items",
        "plant_batches",
        "plants_vegetative",
        "plants_flowering",
        "harvests",
        "sales_receipts",
        "sales_deliveries",
        "transfer_templates",
        "package_tags_available",
        "plant_tags_available",
        "transfer_types",
    } <= resources


def test_strain_read_uses_current_v2_active_path() -> None:
    assert ("strains", "strains/v2/active") in PAGED_RESOURCES


def test_transfer_type_reference_uses_current_v2_path() -> None:
    assert ("transfer_types", "transfers/v2/types") in REFERENCE_RESOURCES


def test_rebaseline_source_is_get_only_and_does_not_materialize_inventory() -> None:
    source = (ROOT / "backend/app/services/metrc_evaluation_rebaseline.py").read_text(encoding="utf-8")
    lowered = source.casefold()

    assert "requests.post" not in lowered
    assert "requests.put" not in lowered
    assert "requests.delete" not in lowered
    assert "canonicalinventoryseeder" not in lowered
    assert '"mutations_sent": 0' in source
    assert "_paged(" in source
    assert "_reference(" in source


def test_candidate_evidence_is_bounded_to_nonsecret_provider_identity() -> None:
    row = {
        "Id": 42,
        "Label": "AAA0A0300000000000000001",
        "Name": "Evaluation fixture",
        "Status": "Active",
        "LastModified": "2026-09-14T16:00:00Z",
        "ApiKey": "must-not-copy",
    }

    assert _candidate(row) == {
        "id": 42,
        "label": "AAA0A0300000000000000001",
        "name": "Evaluation fixture",
        "status": "Active",
        "last_modified": "2026-09-14T16:00:00Z",
    }
