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
    assert "<ExtractionCommandCenterPage" in unified


def test_advanced_run_360_is_context_not_another_navigation_destination():
    unified = read("frontend/src/pages/ExtractionUnifiedPage.tsx")

    assert 'import { WorkspaceWindow } from "../components/WorkspaceWindow"' in unified
    assert "<WorkspaceWindow" in unified
    assert 'windowKey="extraction-run-360"' in unified
    assert 'ariaLabel="Advanced Extraction Run 360"' in unified
    assert "<ExtractionPage" in unified
    assert 'type View = "today" | "runs" | "inventory" | "analytics"' in unified


def test_today_prioritizes_attention_running_and_next_work():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert 'title="Needs attention"' in floor
    assert 'title="Running now"' in floor
    assert 'title="Next up"' in floor
    assert '["hold", "qa"].includes(row.status)' in floor
    assert 'row.status === "active"' in floor
    assert '["planned", "queued"].includes(row.status)' in floor


def test_new_run_starts_from_source_material_instead_of_giant_record_form():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert "Start from source material" in floor
    assert "What are you making?" in floor
    assert "Source material" in floor
    assert 'label="Amount going into run"' in floor
    assert 'label="Run ID"' in floor
    assert "metrc_input_package_id:lot.compliance_package_id" in floor
    assert '`/api/v1/extraction/runs/${run.id}/inputs`' in floor
    assert '`/api/v1/extraction/inputs/${input.id}/consume`' in floor
    assert 'event_type:"started"' in floor
    assert ">Start run</button>" in floor


def test_floor_operator_enters_measurements_while_system_calculates_process_math():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert 'label="Stage input (g)"' in floor
    assert 'label="Scale output (g)"' in floor
    assert "Calculated stage loss" in floor
    assert "Loss %" in floor
    assert "Stage yield" in floor
    assert "Overall yield" in floor
    assert "Recorded process loss" in floor
    assert "Unexplained variance" in floor
    assert "loss_weight_g:null" in floor
    assert "Math.max(0,form.input_weight_g-form.output_weight_g)" in floor
    assert "form.output_weight_g/form.input_weight_g*100" in floor


def test_floor_operator_can_update_run_inline_and_advance_workflow():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    for event in ('"started"', '"measurement"', '"completed"', '"hold"', '"released"'):
        assert event in floor
    assert "Start / mark active" in floor
    assert "Save update" in floor
    assert "Complete & move to next" in floor
    assert "Put on hold" in floor
    assert "Resume run" in floor
    assert "Recent process history" in floor
    assert "Input carried forward" in floor


def test_floor_keeps_traceability_and_formulation_but_progressively_discloses_them():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert "More details / traceability" in floor
    assert "METRC stage input ID" in floor
    assert "METRC stage output ID" in floor
    assert "Intermediate product type" in floor
    assert "Final product type" in floor
    assert "Calculated terpene addition" in floor
    assert "Expected formulated mass" in floor
    assert "Confirm actual scale output" in floor


def test_backend_remains_authoritative_for_deterministic_stage_loss():
    repository = read("modules/extraction/repository.py")

    assert "if loss_weight_g is None and in_weight is not None and out_weight is not None:" in repository
    assert "loss = max(0.0, in_weight - out_weight)" in repository
    assert '"yield_pct": yield_pct' in repository
