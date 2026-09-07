from pathlib import Path

import pytest

from scripts.metrc_workflow_policy import (
    READ_ONLY_OPERATIONS,
    WRITE_CONFIRMATION,
    WRITE_OPERATIONS,
    authorize_operation,
    classify_operation,
    main,
)


def test_facilities_and_workbook_plan_are_read_only():
    assert classify_operation("facilities") == "read_only"
    assert classify_operation("workbook_plan") == "read_only"
    assert "facilities" in READ_ONLY_OPERATIONS


def test_unknown_operation_is_rejected_before_execution():
    with pytest.raises(ValueError, match="bounded MA Metrc evaluation operation"):
        classify_operation("/arbitrary/provider/path")


def test_write_operation_requires_main_and_exact_confirmation():
    assert WRITE_OPERATIONS, "The MA evaluation plan must contain at least one mutation-family operation."
    operation = sorted(WRITE_OPERATIONS)[0]

    with pytest.raises(ValueError, match="only run from refs/heads/main"):
        authorize_operation(
            operation,
            github_ref="refs/heads/feature/unreviewed-metrc-write",
            confirmation=WRITE_CONFIRMATION,
        )

    with pytest.raises(ValueError, match="require confirmation"):
        authorize_operation(operation, github_ref="refs/heads/main", confirmation="yes")

    result = authorize_operation(
        operation,
        github_ref="refs/heads/main",
        confirmation=WRITE_CONFIRMATION,
    )
    assert result["classification"] == "write"
    assert result["write_approved"] is True


def test_cli_writes_classification_without_echoing_confirmation(tmp_path, capsys):
    operation = sorted(WRITE_OPERATIONS)[0]
    github_env = tmp_path / "github-env"
    result = main(
        [
            "--operation",
            operation,
            "--github-ref",
            "refs/heads/main",
            "--confirmation",
            WRITE_CONFIRMATION,
            "--github-env",
            str(github_env),
        ]
    )
    assert result == 0
    stdout = capsys.readouterr().out
    assert WRITE_CONFIRMATION not in stdout
    env_text = github_env.read_text(encoding="utf-8")
    assert "METRC_OPERATION_READ_ONLY=false" in env_text
    assert "METRC_OPERATION_CLASSIFICATION=write" in env_text


def test_manual_workflow_defaults_to_safe_read_and_bounds_full_evidence():
    workflow = Path(".github/workflows/ma-metrc-sandbox-validation.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "default: facilities" in workflow
    assert "scripts/metrc_workflow_policy.py" in workflow
    assert "scripts/validate_ma_metrc_sandbox.py --live-read" in workflow
    assert "I_APPROVE_MA_SANDBOX_WRITE" in workflow
    assert "METRC_INTEGRATOR_API_KEY: ${{ secrets.METRC_INTEGRATOR_API_KEY }}" in workflow
    assert "METRC_MA_SANDBOX_USER_API_KEY: ${{ secrets.METRC_MA_SANDBOX_USER_API_KEY }}" in workflow
    assert "METRC_MA_SANDBOX_LICENSE_NUMBER: ${{ secrets.METRC_MA_SANDBOX_LICENSE_NUMBER }}" in workflow
    assert "default: false" in workflow
    assert "retention-days: 7" in workflow
    assert "Redacted evidence summary" in workflow
