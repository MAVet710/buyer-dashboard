from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from services.metrc_evaluation_finalization import build_final_report
from services.metrc_evaluation_submission import (
    COMPANY_INFORMATION_REQUIRED_FIELDS,
    SECRET_WORKBOOK_FIELDS,
)
from services.metrc_evaluation_workbook import MA_WORKBOOK_TASKS, WORKBOOK_SHEETS


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "artifacts" / "metrc-evaluation" / "verify_final.mjs"


def _company() -> dict[str, str]:
    return {
        field: f"value for {field}"
        for field in COMPANY_INFORMATION_REQUIRED_FIELDS
        if field not in SECRET_WORKBOOK_FIELDS
    }


def _report(tmp_path: Path) -> dict:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for task in MA_WORKBOOK_TASKS:
        (evidence / f"{task.number:02d}-{task.operation_type}.json").write_text(
            json.dumps({
                "task_number": task.number,
                "passed": True,
                "stage": "complete",
                "operation_type": task.operation_type,
                "state": "MA",
                "environment": "sandbox",
                "http_status": 200,
                "provider_id": str(task.number),
                "readback": {"verified": True},
            }),
            encoding="utf-8",
        )
    return build_final_report(evidence_directory=evidence, company_information=_company())


def _manifest() -> dict:
    return {
        "schema_version": 1,
        "sheet_count": 22,
        "sheet_names": list(WORKBOOK_SHEETS),
        "missing_labels": [],
        "missing_values": [],
        "secret_values_recorded": False,
        "secret_fields_filled": {"Vendor Key Used": True, "User Key Used": True},
        "task_result_cells_modified": False,
        "metrc_use_only_cells_modified": False,
        "filled_fields": [
            {"field": "Vendor Key Used", "sheet": "CompanyInformation", "cell": "B12", "secret": True},
            {"field": "User Key Used", "sheet": "CompanyInformation", "cell": "B13", "secret": True},
        ],
    }


def _results_manifest() -> dict:
    return {
        "schema_version": 1,
        "sheet_count": 22,
        "sheet_names": list(WORKBOOK_SHEETS),
        "regulator_action_rows_filled": 46,
        "expected_regulator_action_rows": 46,
        "task_result_cells_modified": True,
        "task_result_cells_modified_count": 46 * 7,
        "permissions_table_modified": True,
        "permissions_table_cells_modified_count": 22,
        "metrc_use_only_cells_modified": False,
        "secret_values_recorded": False,
        "result_edits": [],
        "permission_edits": [],
    }


def _node() -> str:
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node is not installed in this test environment.")
    return executable


def test_verify_final_accepts_ready_redacted_report_and_both_manifests(tmp_path):
    report_path = tmp_path / "final_report.json"
    manifest_path = tmp_path / "submission.manifest.json"
    results_manifest_path = tmp_path / "submission.results.manifest.json"
    report_path.write_text(json.dumps(_report(tmp_path)), encoding="utf-8")
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    results_manifest_path.write_text(json.dumps(_results_manifest()), encoding="utf-8")

    result = subprocess.run(
        [_node(), str(VERIFIER), str(report_path), str(manifest_path), str(results_manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINAL VERIFIED" in result.stdout
    assert "46 regulator action rows" in result.stdout
    assert "No regulator approval is claimed" in result.stdout


def test_verify_final_rejects_credential_like_report_fields(tmp_path):
    report = _report(tmp_path)
    report["user_api_key"] = "must-never-be-here"
    report_path = tmp_path / "final_report.json"
    manifest_path = tmp_path / "submission.manifest.json"
    results_manifest_path = tmp_path / "submission.results.manifest.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    results_manifest_path.write_text(json.dumps(_results_manifest()), encoding="utf-8")

    result = subprocess.run(
        [_node(), str(VERIFIER), str(report_path), str(manifest_path), str(results_manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "Credential-like fields leaked" in result.stderr


def test_verify_final_rejects_blank_task_results_manifest(tmp_path):
    report_path = tmp_path / "final_report.json"
    manifest_path = tmp_path / "submission.manifest.json"
    results_manifest_path = tmp_path / "submission.results.manifest.json"
    report_path.write_text(json.dumps(_report(tmp_path)), encoding="utf-8")
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    bad = _results_manifest() | {"task_result_cells_modified": False, "regulator_action_rows_filled": 0}
    results_manifest_path.write_text(json.dumps(bad), encoding="utf-8")

    result = subprocess.run(
        [_node(), str(VERIFIER), str(report_path), str(manifest_path), str(results_manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "did not populate all 46" in result.stderr
