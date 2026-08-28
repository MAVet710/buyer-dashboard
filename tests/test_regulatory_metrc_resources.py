from __future__ import annotations

import pytest

from modules.regulatory import RegulatoryReadError, build_metrc_read_plan, normalize_metrc_payload


def test_massachusetts_package_plan_is_license_scoped_and_evidence_backed():
    plan = build_metrc_read_plan(
        jurisdiction="MA",
        resource="packages_active",
        environment="production",
        license_number="LIC-123",
        page_size=50,
        page_number=2,
    )

    assert plan.jurisdiction_code == "MA"
    assert plan.capability == "packages"
    assert plan.path == "packages/v2/active"
    assert plan.params == {"licenseNumber": "LIC-123", "pageSize": 50, "pageNumber": 2}
    assert plan.evidence is not None
    assert plan.evidence.source_url == "https://api-ma.metrc.com/Documentation/"


def test_unverified_jurisdiction_resource_fails_closed():
    with pytest.raises(RegulatoryReadError, match="unknown/unverified"):
        build_metrc_read_plan(
            jurisdiction="RI",
            resource="packages_active",
            environment="production",
            license_number="RI-1",
        )


def test_plan_rejects_license_substitution_in_query_parameters():
    with pytest.raises(RegulatoryReadError, match="cannot substitute"):
        build_metrc_read_plan(
            jurisdiction="MA",
            resource="lab_results",
            environment="production",
            license_number="LIC-123",
            query={"licenseNumber": "OTHER-LICENSE", "packageId": 55},
        )


def test_path_parameter_is_required_and_encoded():
    with pytest.raises(RegulatoryReadError, match="transfer_id"):
        build_metrc_read_plan(
            jurisdiction="MA",
            resource="transfer_deliveries",
            environment="production",
        )

    plan = build_metrc_read_plan(
        jurisdiction="MA",
        resource="transfer_deliveries",
        environment="production",
        path_parameters={"transfer_id": "12/../../../x"},
    )
    assert plan.path == "transfers/v2/12%2F..%2F..%2F..%2Fx/deliveries"


def test_normalization_preserves_provider_record_losslessly():
    source = {
        "Id": 41,
        "Label": "1A4000000000000000000041",
        "ItemName": "Flower Bulk",
        "Quantity": 1200.5,
        "UnitOfMeasureAbbreviation": "g",
        "LabTestingState": "TestPassed",
        "CustomStateField": {"kept": True},
    }
    records = normalize_metrc_payload(
        jurisdiction="MA",
        resource="packages_active",
        payload={"Data": [source], "TotalPages": 1},
    )

    assert len(records) == 1
    record = records[0]
    assert record["provider"] == "metrc"
    assert record["jurisdiction_code"] == "MA"
    assert record["resource"] == "packages_active"
    assert record["provider_id"] == "41"
    assert record["label"] == "1A4000000000000000000041"
    assert record["name"] == "Flower Bulk"
    assert record["quantity"] == 1200.5
    assert record["unit_of_measure"] == "g"
    assert record["status"] == "TestPassed"
    assert record["source"] == source
