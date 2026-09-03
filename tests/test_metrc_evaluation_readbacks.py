from __future__ import annotations

from modules.regulatory import build_metrc_read_plan, normalize_metrc_payload
from modules.regulatory.registry import CapabilityStatus, capability_status


def test_massachusetts_strains_are_a_verified_metrc_capability():
    assert capability_status("MA", "strains") == CapabilityStatus.JURISDICTION_SPECIFIC

    plan = build_metrc_read_plan(
        jurisdiction="MA",
        resource="strains_active",
        environment="sandbox",
        license_number="MA-SANDBOX-LIC",
    )
    assert plan.path == "strains/v2/active"
    assert plan.params["licenseNumber"] == "MA-SANDBOX-LIC"
    assert plan.evidence is not None
    assert plan.evidence.endpoint == "GET /strains/v2/active"


def test_evaluation_master_data_readbacks_are_exact_by_id_and_license_scoped():
    cases = {
        "locations_by_id": "locations/v2/41",
        "strains_by_id": "strains/v2/41",
        "items_by_id": "items/v2/41",
    }
    for resource, expected_path in cases.items():
        plan = build_metrc_read_plan(
            jurisdiction="MA",
            resource=resource,
            environment="sandbox",
            license_number="MA-SANDBOX-LIC",
            path_parameters={"id": 41},
        )
        assert plan.path == expected_path
        assert plan.params == {"licenseNumber": "MA-SANDBOX-LIC"}


def test_evaluation_lifecycle_readbacks_cover_created_provider_objects():
    cases = {
        "plant_batches_by_id": "plantbatches/v2/51",
        "plants_by_id": "plants/v2/51",
        "harvests_by_id": "harvests/v2/51",
        "packages_by_id": "packages/v2/51",
        "processing_by_id": "processing/v2/51",
        "sales_receipts_by_id": "sales/v2/receipts/51",
        "sales_deliveries_by_id": "sales/v2/deliveries/51",
    }
    for resource, expected_path in cases.items():
        plan = build_metrc_read_plan(
            jurisdiction="MA",
            resource=resource,
            environment="sandbox",
            license_number="MA-SANDBOX-LIC",
            path_parameters={"id": 51},
        )
        assert plan.path == expected_path
        assert plan.params == {"licenseNumber": "MA-SANDBOX-LIC"}


def test_rejected_transfer_evaluation_read_is_normalized_and_paginated():
    plan = build_metrc_read_plan(
        jurisdiction="MA",
        resource="rejected_transfers",
        environment="sandbox",
        license_number="MA-SANDBOX-LIC",
        page_size=100,
        page_number=2,
    )
    assert plan.path == "transfers/v2/rejected"
    assert plan.params == {
        "licenseNumber": "MA-SANDBOX-LIC",
        "pageSize": 100,
        "pageNumber": 2,
    }


def test_by_id_object_payload_normalizes_as_one_lossless_record():
    source = {
        "Id": 77,
        "Name": "Evaluation Room",
        "LastModified": "2026-09-03T20:00:00Z",
        "LocationTypeName": "Default",
    }
    records = normalize_metrc_payload(
        jurisdiction="MA",
        resource="locations_by_id",
        payload=source,
    )
    assert len(records) == 1
    assert records[0]["provider_id"] == "77"
    assert records[0]["name"] == "Evaluation Room"
    assert records[0]["last_modified"] == "2026-09-03T20:00:00Z"
    assert records[0]["source"] == source
