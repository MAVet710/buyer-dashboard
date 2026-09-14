from __future__ import annotations

from pathlib import Path

from services.metrc_evaluation_instruction_contract import (
    INTERNAL_CHECK_COUNT,
    MA_PERMISSION_DEPENDENCIES,
    PREREQUISITE_CHECK_COUNT,
    REGULATOR_ACTION_COUNT,
    USER_KEY_POLICY,
    ma_instruction_contract,
    operation_facility_profile,
    operation_required_capabilities,
)
from services.metrc_evaluation_workbook import (
    MA_CONTEXT_SHEETS,
    MA_NA_SHEETS,
    MA_PREREQUISITE_CHECKS,
    MA_REGULATOR_ACTION_TASKS,
    MA_WORKBOOK_TASKS,
    ma_workbook_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def test_workbook_count_split_preserves_evidence_numbering_without_overstating_regulator_rows() -> None:
    plan = ma_workbook_plan()
    assert REGULATOR_ACTION_COUNT == 46
    assert PREREQUISITE_CHECK_COUNT == 1
    assert INTERNAL_CHECK_COUNT == 47
    assert plan["applicable_task_count"] == 46
    assert plan["regulator_action_count"] == 46
    assert plan["prerequisite_check_count"] == 1
    assert plan["internal_check_count"] == 47
    assert len(MA_WORKBOOK_TASKS) == 47
    assert len(MA_PREREQUISITE_CHECKS) == 1
    assert len(MA_REGULATOR_ACTION_TASKS) == 46
    assert MA_PREREQUISITE_CHECKS[0].operation_type == "facilities"
    assert [task.number for task in MA_WORKBOOK_TASKS] == list(range(1, 48))


def test_open_loop_ma_uses_closed_loop_environment_as_context_not_na_task_sheet() -> None:
    plan = ma_workbook_plan()
    by_sheet = {row["sheet"].rstrip(): row["status"] for row in plan["sheets"]}
    assert "Closed Loop Environment" in MA_CONTEXT_SHEETS
    assert "Closed Loop Environment" not in MA_NA_SHEETS
    assert by_sheet["Closed Loop Environment"] == "context"
    assert by_sheet["Closed Loop States PlantBatches"] == "not_applicable_ma"


def test_permission_dependencies_match_workbook_d_and_o_matrix() -> None:
    assert MA_PERMISSION_DEPENDENCIES["grow"]["required"] == (
        "Locations",
        "Strains",
        "Plant Batches / Plants",
        "Harvests",
        "Items",
        "Packages",
        "GET Transfers / Wholesale",
    )
    assert MA_PERMISSION_DEPENDENCIES["processor"]["required"] == (
        "Strains",
        "Items",
        "Packages",
        "GET Transfers / Wholesale",
    )
    assert MA_PERMISSION_DEPENDENCIES["labs"]["required"] == (
        "Strains",
        "Packages",
        "Labs",
        "GET Transfers / Wholesale",
    )
    assert "Items" in MA_PERMISSION_DEPENDENCIES["labs"]["optional"]
    assert MA_PERMISSION_DEPENDENCIES["sales"]["required"] == (
        "Strains",
        "Items",
        "Packages",
        "Sales",
        "Sales Deliveries",
        "GET Transfers / Wholesale",
    )


def test_rerun_policy_reuses_existing_user_key_and_forbids_bootstrap_generation() -> None:
    contract = ma_instruction_contract()
    assert USER_KEY_POLICY["mode"] == "reuse_existing_only"
    assert USER_KEY_POLICY["bootstrap_endpoint_allowed"] is False
    assert USER_KEY_POLICY["generate_user_key_allowed"] is False
    assert USER_KEY_POLICY["rotate_user_key_allowed"] is False
    assert contract["user_key_policy"] == USER_KEY_POLICY

    runner = (ROOT / "scripts/run_ma_metrc_evaluation.py").read_text(encoding="utf-8")
    lowered = runner.casefold()
    assert "setup_ma_sandbox_integrator" not in runner
    assert "/sandbox/v2/integrator/setup" not in lowered
    assert "provision-user" not in lowered
    assert "resolve_ma_sandbox_evaluation_credentials" in runner
    assert "selected_license_match_count" in runner


def test_operation_profiles_prevent_grow_license_from_being_treated_as_lab_or_sales() -> None:
    assert operation_facility_profile("plant_harvest") == "grow"
    assert operation_required_capabilities("plant_harvest") == ("CanGrowPlants",)
    assert operation_facility_profile("lab_test_record") == "labs"
    assert operation_required_capabilities("lab_test_record") == ("CanTestPackages",)
    assert operation_facility_profile("sales_receipt_create") == "sales"
    assert "CanSellToConsumers" in operation_required_capabilities("sales_receipt_create")
    assert operation_facility_profile("sales_delivery_create") == "sales"
    assert "CanDeliverSalesToConsumers" in operation_required_capabilities("sales_delivery_create")
    assert operation_facility_profile("transfer_template_create") == "transfers"
    assert operation_required_capabilities("transfer_template_create") == ()


def test_runner_and_workflow_require_explicit_per_action_license_instead_of_global_license() -> None:
    runner = (ROOT / "scripts/run_ma_metrc_evaluation.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ma-metrc-sandbox-validation.yml").read_text(encoding="utf-8")
    assert '--license-number' in runner
    assert "--license-number is required" in runner
    assert "METRC_MA_SANDBOX_LICENSE_NUMBER: ${{ secrets.METRC_MA_SANDBOX_LICENSE_NUMBER }}" not in workflow
    assert "license_number:" in workflow
    assert '--license-number "$SELECTED_LICENSE"' in workflow
    assert "METRC_MA_SANDBOX_USER_API_KEY: ${{ secrets.METRC_MA_SANDBOX_USER_API_KEY }}" in workflow


def test_task_specific_workbook_rules_are_preserved_in_plan() -> None:
    by_operation = {task.operation_type: task for task in MA_WORKBOOK_TASKS}
    assert "same calendar day" in by_operation["plant_harvest"].note
    assert "Moisture loss" in by_operation["harvest_waste"].note
    assert "existing package in the Lab" in by_operation["lab_test_record"].note
    assert "exactly three transactions" in by_operation["sales_delivery_create"].note
