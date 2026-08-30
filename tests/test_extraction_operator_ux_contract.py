from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_extraction_uses_job_first_four_surface_navigation():
    unified = read("frontend/src/pages/ExtractionUnifiedPage.tsx")

    assert 'useState<View>("today")' in unified
    for label in ("Today", "Runs", "Inventory", "Analytics"):
        assert f">{label}</button>" in unified
    assert "Run Floor" not in unified
    assert "Command Center</button>" not in unified
    assert '<ExtractionOperatorWorkspace mode="today"' in unified
    assert '<ExtractionOperatorWorkspace mode="runs"' in unified
    assert "<ExtractionAnalyticsWorkspace" in unified
    assert "<ExtractionCommandCenterPage" in unified


def test_advanced_run_360_is_context_not_another_navigation_destination():
    unified = read("frontend/src/pages/ExtractionUnifiedPage.tsx")

    assert 'import { WorkspaceWindow } from "../components/WorkspaceWindow"' in unified
    assert "<WorkspaceWindow" in unified
    assert 'windowKey="extraction-run-360"' in unified
    assert 'ariaLabel="Advanced Extraction Run 360"' in unified
    assert "<ExtractionPage" in unified
    assert 'type View = "today" | "runs" | "inventory" | "analytics"' in unified
    assert "Management & Compliance" in unified


def test_today_prioritizes_attention_running_and_next_work():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert 'title="Needs attention"' in floor
    assert 'title="Running now"' in floor
    assert 'title="Next up"' in floor
    assert '["hold", "qa"].includes(row.status)' in floor
    assert 'row.status === "active"' in floor
    assert '["planned", "queued"].includes(row.status)' in floor


def test_new_run_plans_and_reserves_without_automatic_consumption():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert "Reserve source material" in floor
    assert "Process / target" in floor
    assert "Source material" in floor
    assert 'label="Amount to reserve"' in floor
    assert 'label="Run ID"' in floor
    assert "metrc_input_package_id:lot.compliance_package_id" in floor
    assert '`/api/v1/extraction/runs/${run.id}/inputs`' in floor
    assert "Reserving does not consume the package." in floor
    assert "Plan run & reserve" in floor
    quick_start = floor.split("function QuickStartRun", 1)[1].split("function RunGroup", 1)[0]
    assert '/consume`' not in quick_start
    assert 'event_type:"started"' not in quick_start


def test_selected_run_and_new_run_are_mutually_exclusive():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert 'const selectRun=(runId:string)=>{setSelected(runId);setCreating(false)};' in floor
    assert 'const openNewRun=()=>{setSelected("");setCreating(true)};' in floor
    assert "if (selected || creating) return;" in floor
    assert "onSelect={selectRun}" in floor


def test_floor_has_explicit_preflight_before_consumption_and_start():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    for marker in (
        "Preflight",
        "Source package/material verified",
        "Required equipment/work area ready",
        "Required SOP/batch documentation ready",
    ):
        assert marker in floor
    assert "Start run & consume reserved material" in floor
    assert '/api/v1/extraction/inputs/${input.id}/consume' in floor
    assert 'event_type:"started"' in floor


def test_floor_operator_enters_measurements_while_system_calculates_process_math():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert 'label="Stage input (g)"' in floor
    assert 'label="Scale output (g)"' in floor
    assert "Calculated stage loss" in floor
    assert "Loss %" in floor
    assert "Stage yield" in floor
    assert "Overall yield" in floor
    assert "Unexplained variance" in floor
    assert "loss_weight_g:null" in floor
    assert "Math.max(0,form.input_weight_g-form.output_weight_g)" in floor
    assert "form.output_weight_g/form.input_weight_g*100" in floor


def test_floor_operator_has_broader_process_actions_and_optional_step_control():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    for event in ('"started"', '"measurement"', '"completed"', '"hold"', '"released"', '"note"', '"deviation"'):
        assert event in floor
    for label in (
        "Save measurement",
        "Add process note",
        "Record deviation / rework",
        "Put on hold",
        "Resume run",
        "Skip optional step",
        "Complete step",
        "Recent process history",
        "Input carried forward",
    ):
        assert label in floor


def test_floor_hands_output_qa_release_and_deep_traceability_to_run_360():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert "Open Run 360" in floor
    assert "Create intermediate / output" in floor
    assert "QA / COA / release" in floor
    assert "METRC stage input ID" in floor
    assert "METRC stage output ID" in floor
    assert "Intermediate product type" in floor
    assert "Final product type" in floor
    assert "Calculated terpene addition" in floor
    assert "Expected formulated mass" in floor


def test_primary_analytics_is_focused_on_performance_not_data_entry():
    analytics = read("frontend/src/pages/ExtractionAnalyticsWorkspace.tsx")

    assert "Extraction analytics" in analytics
    assert "Method comparison" in analytics
    assert "Avg yield" in analytics
    assert "Recorded loss" in analytics
    assert "COGS" in analytics
    assert "Data entry stays on Today/Runs" in analytics


def test_backend_remains_authoritative_for_deterministic_stage_loss():
    repository = read("modules/extraction/repository.py")

    assert "if loss_weight_g is None and in_weight is not None and out_weight is not None:" in repository
    assert "loss = max(0.0, in_weight - out_weight)" in repository
    assert '"yield_pct": yield_pct' in repository
