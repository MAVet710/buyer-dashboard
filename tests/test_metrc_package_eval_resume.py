from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend" / "app" / "services" / "metrc_package_eval_resume.py"
PACKAGE_INIT = ROOT / "backend" / "app" / "__init__.py"


def test_package_eval_hook_is_explicit_runtime_opt_in():
    source = PACKAGE_INIT.read_text(encoding="utf-8")
    assert "METRC_PACKAGE_EVAL_RUN_ID" in source
    assert "if not run_id" in source
    assert "run_package_tasks_25_26" in source


def test_package_eval_is_ma_sandbox_only_and_bounded_to_25_26():
    source = SERVICE.read_text(encoding="utf-8")
    assert 'resolve_metrc_base_url("MA", environment="sandbox")' in source
    assert 'metrc.environment == "sandbox"' in source
    assert "metrc.trusted_mapping" in source
    assert 'operation_type="package_create"' in source
    assert 'operation_type="package_item"' in source
    assert 'operation_type="package_adjust"' not in source
    assert 'operation_type="package_finish"' not in source
    assert 'operation_type="package_unfinish"' not in source


def test_package_eval_uses_existing_regulator_permitted_source_package():
    source = SERVICE.read_text(encoding="utf-8")
    assert 'SOURCE_ITEM = f"{EVALUATION_BASE_RUN}-Clones"' in source
    assert '"PackageType"' in source
    assert '"immatureplant"' in source
    assert '"dependency_basis"' in source
    assert "existing package" in source.casefold()


def test_package_eval_never_uses_an_unattributed_existing_available_tag():
    source = SERVICE.read_text(encoding="utf-8")
    assert "sandbox/v2/facility/tags" in source
    assert "sandbox/v2/tagtypes" in source
    assert 'action="plan"' in source
    assert 'action="tag_generated"' in source
    assert "available_tags_before" in source
    assert "delta = [label for label in current if label not in set(before)]" in source
    assert "More than one new package tag appeared" in source


def test_package_eval_blocks_blind_retry_after_uncertain_write():
    source = SERVICE.read_text(encoding="utf-8")
    assert 'action="task25_attempt_started"' in source
    assert 'action="task25_outcome_uncertain"' in source
    assert 'action="task26_attempt_started"' in source
    assert 'action="task26_outcome_uncertain"' in source
    assert "blind retry blocked" in source


def test_package_eval_requires_http200_plus_existing_evaluator_readback():
    source = SERVICE.read_text(encoding="utf-8")
    assert "execute_lifecycle_evaluation_action" in source
    assert 'e25.get("passed") is not True' in source
    assert 'e26.get("passed") is True' in source
    assert 'e25["task_number"] = 25' in source
    assert 'e26["task_number"] = 26' in source
