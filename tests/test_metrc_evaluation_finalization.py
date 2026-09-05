from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.metrc_evaluation_finalization import (
    MetrcEvaluationFinalizationError,
    build_final_report,
)
from services.metrc_evaluation_submission import (
    COMPANY_INFORMATION_REQUIRED_FIELDS,
    SECRET_WORKBOOK_FIELDS,
)
from services.metrc_evaluation_workbook import MA_WORKBOOK_TASKS


def _company_information() -> dict[str, str]:
    return {
        field: f"value for {field}"
        for field in COMPANY_INFORMATION_REQUIRED_FIELDS
        if field not in SECRET_WORKBOOK_FIELDS
    }


def _write_evidence(root: Path, *, failed_task: int | None = None, omit_task: int | None = None) -> None:
    for task in MA_WORKBOOK_TASKS:
        if task.number == omit_task:
            continue
        passed = task.number != failed_task
        payload = {
            "task_number": task.number,
            "passed": passed,
            "stage": "complete" if passed else "readback_identity",
            "operation_type": task.operation_type,
            "state": "MA",
            "environment": "sandbox",
            "license_number": "MP281234",
            "http_status": 200,
            "provider_id": str(10_000 + task.number),
            "correlation_id": f"task-{task.number}",
            "readback": {"verified": passed},
        }
        (root / f"{task.number:02d}-{task.operation_type}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def test_final_report_requires_all_47_http_200_completed_passed_evidence(tmp_path):
    _write_evidence(tmp_path)
    report = build_final_report(
        evidence_directory=tmp_path,
        company_information=_company_information(),
    )

    assert report["submission_ready"] is True
    assert report["status"] == "ready_for_metrc_review"
    assert report["regulator_approval_claimed"] is False
    assert report["summary"] == {
        "passed": 47,
        "failed": 0,
        "missing": 0,
        "total": 47,
        "evidence_files_seen": 47,
        "extra_or_unmatched_evidence": 0,
    }
    assert [row["number"] for row in report["tasks"]] == list(range(1, 48))
    assert all(row["status"] == "passed" for row in report["tasks"])
    assert set(report["company_information"]).isdisjoint(SECRET_WORKBOOK_FIELDS)


def test_final_report_fails_closed_for_failed_or_missing_task_evidence(tmp_path):
    _write_evidence(tmp_path, failed_task=27, omit_task=41)
    report = build_final_report(
        evidence_directory=tmp_path,
        company_information=_company_information(),
    )

    assert report["submission_ready"] is False
    assert report["status"] == "not_ready"
    assert report["summary"]["passed"] == 45
    assert report["summary"]["failed"] == 1
    assert report["summary"]["missing"] == 1
    by_number = {row["number"]: row for row in report["tasks"]}
    assert by_number[27]["status"] == "failed"
    assert "stage_not_complete" in by_number[27]["reasons"]
    assert "runner_not_passed" in by_number[27]["reasons"]
    assert by_number[41]["status"] == "missing"


def test_final_report_requires_non_secret_company_information(tmp_path):
    _write_evidence(tmp_path)
    company = _company_information()
    company.pop("Primary Contact Email")
    report = build_final_report(evidence_directory=tmp_path, company_information=company)

    assert report["submission_ready"] is False
    assert report["summary"]["passed"] == 47
    assert report["missing_company_information"] == ["Primary Contact Email"]


def test_final_report_rejects_company_json_with_vendor_or_user_keys(tmp_path):
    _write_evidence(tmp_path)
    company = _company_information() | {"Vendor Key Used": "do-not-store-this"}

    with pytest.raises(MetrcEvaluationFinalizationError, match="must not be supplied"):
        build_final_report(evidence_directory=tmp_path, company_information=company)


def test_final_report_rejects_credential_like_fields_in_evidence(tmp_path):
    _write_evidence(tmp_path)
    target = tmp_path / "01-facilities.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["user_api_key"] = "do-not-store-this"
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MetrcEvaluationFinalizationError, match="credential-like"):
        build_final_report(
            evidence_directory=tmp_path,
            company_information=_company_information(),
        )


def test_duplicate_transfer_template_create_evidence_can_be_assigned_without_task_hints(tmp_path):
    _write_evidence(tmp_path)
    for number in (43, 44):
        old = tmp_path / f"{number:02d}-transfer_template_create.json"
        payload = json.loads(old.read_text(encoding="utf-8"))
        payload.pop("task_number")
        old.unlink()
        (tmp_path / f"template-{number}.json").write_text(json.dumps(payload), encoding="utf-8")

    report = build_final_report(
        evidence_directory=tmp_path,
        company_information=_company_information(),
    )
    by_number = {row["number"]: row for row in report["tasks"]}
    assert by_number[43]["status"] == "passed"
    assert by_number[44]["status"] == "passed"
    assert report["summary"]["extra_or_unmatched_evidence"] == 0
