from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_invariants_document_exists_and_preserves_local_first_contract() -> None:
    policy = _read("docs/PROJECT_INVARIANTS.md")
    assert "local stack" in policy
    assert "Do not assume Render" in policy
    assert "current owner/developer account" in policy
    assert "`God`" in policy


def test_username_login_contract_remains_username_first_and_case_insensitive() -> None:
    frontend = _read("frontend/src/components/AuthGate.tsx")
    account = _read("backend/app/routers/account.py")

    assert '/api/v1/account/username-login' in frontend
    assert 'username: value' in frontend
    assert 'value.includes("@")' in frontend
    assert '@router.post("/username-login")' in account
    assert 'payload.username.strip().casefold()' in account
    assert 'AppUser.normalized_username == normalized_username' in account
    assert 'auth_session["auth_user_id"] != app_user_id' in account
    assert '@users.doobielogic.io' not in frontend


def test_metrc_evaluation_runner_can_never_provision_or_rotate_user_key() -> None:
    runner = _read("scripts/run_ma_metrc_evaluation.py").casefold()
    assert "setup_ma_sandbox_integrator" not in runner
    assert "integrator/setup" not in runner
    assert "provision-user" not in runner
    assert "rotate" not in runner
    assert "replace the user key" not in runner


def test_metrc_contract_keeps_regulator_and_internal_counts_distinct() -> None:
    runner = _read("scripts/run_ma_metrc_evaluation.py")
    assert "REGULATOR_ACTION_ROW_COUNT = 46" in runner
    assert "INTERNAL_PREREQUISITE_COUNT = 1" in runner
    assert 'plan["internal_check_count"]' in runner


def test_ma_closed_loop_environment_remains_context_not_closed_loop_task_requirement() -> None:
    runner = _read("scripts/run_ma_metrc_evaluation.py")
    policy = _read("docs/PROJECT_INVARIANTS.md")
    assert '"closed_loop_environment_sheet_required_as_context": True' in runner
    assert '"closed_loop_states_plantbatches_task_sheet_applicable": False' in runner
    assert "`Closed Loop Environment ` is Massachusetts open-loop setup context" in policy


def test_task17_is_guarded_but_not_removed_or_marked_na() -> None:
    runner = _read("scripts/run_ma_metrc_evaluation.py")
    workbook = _read("services/metrc_evaluation_workbook.py")
    policy = _read("docs/PROJECT_INVARIANTS.md")
    assert "execute_task17_evaluation_action" in runner
    assert '"plant_plantbatch_packages"' in workbook
    assert "Do not mark it N/A" in policy
    assert "Do not blindly retry it" in policy
