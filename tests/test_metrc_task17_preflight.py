from __future__ import annotations

from pathlib import Path

import pytest

from services.metrc_task17_preflight import (
    TASK17_CAPABILITY,
    TASK17_OPERATION,
    execute_task17_evaluation_action,
    task17_facility_capability_preflight,
)


LICENSE = "SF-SBX-MA-4-11701"
ROOT = Path(__file__).resolve().parents[1]


def _facilities(capability=True, *, duplicates: int = 1):
    records = []
    for index in range(duplicates):
        records.append({
            "license_number": LICENSE,
            "source": {
                "Id": 6704 + index,
                "LicenseNumber": LICENSE,
                "FacilityType": {TASK17_CAPABILITY: capability},
            },
        })
    return {"ok": True, "http_status": 200, "records": records}


def _kwargs():
    return {
        "operation_type": TASK17_OPERATION,
        "payload": {
            "plant_label": "AAA0A0200001A30000000059",
            "package_tag": "AAA0A0300001A30000000024",
            "plant_batch_type": "Clone",
            "item": "DL-EVAL-20260912-RESUME-01-Clones",
            "count": 1,
            "actual_date": "2026-09-12",
        },
        "license_number": LICENSE,
        "integrator_api_key": "vendor-fixture",
        "user_api_key": "user-fixture",
        "state": "MA",
        "environment": "sandbox",
    }


def test_explicit_false_blocks_before_task17_write() -> None:
    writes = []

    evidence = execute_task17_evaluation_action(
        **_kwargs(),
        facilities_read_fn=lambda **_: _facilities(False),
        lifecycle_execute_fn=lambda **kwargs: writes.append(kwargs) or {"passed": True},
    )

    assert evidence["passed"] is False
    assert evidence["stage"] == "facility_capability"
    assert evidence["capability_value"] is False
    assert evidence["write_sent"] is False
    assert writes == []
    assert "explicitly reports" in evidence["message"]


def test_missing_capability_fails_closed_before_write() -> None:
    result = _facilities(True)
    result["records"][0]["source"]["FacilityType"] = {}
    writes = []

    evidence = execute_task17_evaluation_action(
        **_kwargs(),
        facilities_read_fn=lambda **_: result,
        lifecycle_execute_fn=lambda **kwargs: writes.append(kwargs) or {"passed": True},
    )

    assert evidence["passed"] is False
    assert evidence["capability_value"] is None
    assert writes == []


def test_failed_facility_read_blocks_without_write_and_uses_one_attempt() -> None:
    captured = {}
    writes = []

    def read(**kwargs):
        captured.update(kwargs)
        return {"ok": False, "http_status": 401, "message": "Metrc rejected the scoped request."}

    evidence = execute_task17_evaluation_action(
        **_kwargs(),
        facilities_read_fn=read,
        lifecycle_execute_fn=lambda **kwargs: writes.append(kwargs) or {"passed": True},
    )

    assert evidence["http_status"] == 401
    assert evidence["write_sent"] is False
    assert captured["resource"] == "facilities"
    assert captured["max_attempts"] == 1
    assert writes == []


def test_ambiguous_exact_license_blocks_without_write() -> None:
    writes = []
    evidence = execute_task17_evaluation_action(
        **_kwargs(),
        facilities_read_fn=lambda **_: _facilities(True, duplicates=2),
        lifecycle_execute_fn=lambda **kwargs: writes.append(kwargs) or {"passed": True},
    )
    assert evidence["matching_facility_count"] == 2
    assert evidence["passed"] is False
    assert writes == []


def test_explicit_true_allows_exact_task17_executor_only() -> None:
    calls = []

    def lifecycle(**kwargs):
        calls.append(kwargs)
        return {"passed": True, "stage": "complete", "http_status": 200}

    evidence = execute_task17_evaluation_action(
        **_kwargs(),
        facilities_read_fn=lambda **_: _facilities(True),
        lifecycle_execute_fn=lifecycle,
    )

    assert evidence["passed"] is True
    assert len(calls) == 1
    assert calls[0]["operation_type"] == TASK17_OPERATION
    assert calls[0]["license_number"] == LICENSE
    assert evidence["facility_capability_preflight"]["capability_value"] is True


def test_guard_rejects_any_non_task17_operation() -> None:
    args = _kwargs()
    args["operation_type"] = "plant_delete"
    with pytest.raises(ValueError, match="only accepts"):
        execute_task17_evaluation_action(**args)


def test_runner_routes_task17_through_guarded_executor() -> None:
    source = (ROOT / "scripts/run_ma_metrc_evaluation.py").read_text(encoding="utf-8")
    assert "execute_task17_evaluation_action" in source
    assert "TASK17_OPERATION" in source
    assert "if args.operation == TASK17_OPERATION" in source


def test_evaluation_runner_is_postman_equivalent_and_never_bootstraps_user_key() -> None:
    source = (ROOT / "scripts/run_ma_metrc_evaluation.py").read_text(encoding="utf-8")
    lowered = source.casefold()

    assert "setup_ma_sandbox_integrator" not in source
    assert "integrator/setup" not in lowered
    assert "provision-user" not in lowered
    assert "resolve_ma_sandbox_evaluation_credentials" in source
    assert 'integrator_key = credentials.integrator_api_key' in source
    assert 'user_key = credentials.user_api_key' in source
