from __future__ import annotations

from pathlib import Path

from scripts.run_ma_metrc_evaluation import (
    INTERNAL_PREREQUISITE_COUNT,
    REGULATOR_ACTION_ROW_COUNT,
    _annotate_workbook_plan,
)
from services.metrc_evaluation_submission import MA_WORKBOOK_INSTRUCTIONS, ma_submission_context
from services.metrc_evaluation_workbook import ma_workbook_plan


ROOT = Path(__file__).resolve().parents[1]


def test_regulator_action_count_is_distinct_from_internal_facilities_prerequisite() -> None:
    plan = _annotate_workbook_plan(ma_workbook_plan())

    assert REGULATOR_ACTION_ROW_COUNT == 46
    assert INTERNAL_PREREQUISITE_COUNT == 1
    assert plan["regulator_action_row_count"] == 46
    assert plan["internal_prerequisite_count"] == 1
    assert plan["internal_check_count"] == 47
    assert "46 explicit regulator action rows" in plan["counting_note"]


def test_massachusetts_uses_closed_loop_environment_sheet_as_open_loop_context() -> None:
    plan = _annotate_workbook_plan(ma_workbook_plan())
    context = plan["ma_open_loop_context"]

    assert context["closed_loop_environment_sheet_required_as_context"] is True
    assert context["closed_loop_states_plantbatches_task_sheet_applicable"] is False


def test_rerun_contract_reuses_existing_user_key_and_disables_bootstrap() -> None:
    plan = _annotate_workbook_plan(ma_workbook_plan())
    policy = plan["credential_policy"]
    submission = ma_submission_context()

    assert policy["reuse_existing_user_api_key"] is True
    assert policy["generate_user_api_key"] is False
    assert policy["call_integrator_setup"] is False
    assert submission["rerun"]["existing_user_key_only"] is True
    assert submission["rerun"]["bootstrap_allowed"] is False
    assert "reuse the existing active API User Key" in MA_WORKBOOK_INSTRUCTIONS["user_key_reuse"]


def test_runner_source_contains_no_user_key_bootstrap_path() -> None:
    source = (ROOT / "scripts/run_ma_metrc_evaluation.py").read_text(encoding="utf-8")
    lowered = source.casefold()

    assert "setup_ma_sandbox_integrator" not in source
    assert "integrator/setup" not in lowered
    assert "provision-user" not in lowered
