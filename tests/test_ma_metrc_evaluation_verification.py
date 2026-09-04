from __future__ import annotations

import pytest

from services.metrc_evaluation_verification import (
    MetrcWorkbookVerificationError,
    verify_transfer_workbook_read,
)


def test_transfer_workbook_read_does_not_pass_on_empty_http_200_collection():
    result = verify_transfer_workbook_read(
        "transfer_incoming",
        {},
        {"passed": True, "stage": "complete", "records": [], "http_status": 200},
    )
    assert result["passed"] is False
    assert result["stage"] == "verification"


def test_template_list_requires_both_created_template_expectations():
    with pytest.raises(MetrcWorkbookVerificationError, match="both templates"):
        verify_transfer_workbook_read(
            "transfer_template_list",
            {"expected_provider_ids": ["101"]},
            {"passed": True, "records": [{"provider_id": "101", "source": {"Id": 101}}]},
        )


def test_template_list_verifies_both_expected_ids_across_combined_pages():
    result = verify_transfer_workbook_read(
        "transfer_template_list",
        {"expected_provider_ids": ["101", "202"]},
        {
            "passed": True,
            "stage": "complete",
            "records": [
                {"provider_id": "101", "source": {"Id": 101, "Name": "Template A"}},
                {"provider_id": "202", "source": {"Id": 202, "Name": "Template B"}},
            ],
        },
    )
    assert result["passed"] is True
    assert result["record_count"] == 2


def test_template_list_fails_when_second_expected_template_is_missing():
    result = verify_transfer_workbook_read(
        "transfer_template_list",
        {"expected_names": ["Template A", "Template B"]},
        {
            "passed": True,
            "stage": "complete",
            "records": [{"provider_id": "101", "source": {"Id": 101, "Name": "Template A"}}],
        },
    )
    assert result["passed"] is False
    assert result["stage"] == "verification"
    assert result["observed_names"] == ["Template A"]
