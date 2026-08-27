from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_extraction_defaults_to_floor_workflow_without_removing_advanced_tools():
    unified = read("frontend/src/pages/ExtractionUnifiedPage.tsx")

    assert 'useState<View>("floor")' in unified
    assert ">Run Floor</button>" in unified
    assert ">Analytics</button>" in unified
    assert ">Inventory</button>" in unified
    assert "<ExtractionOperatorWorkspace" in unified
    assert "<ExtractionCommandCenterPage" in unified
    assert "<ExtractionPage" in unified
    assert "Advanced Run 360" in unified


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
    assert "loss_weight_g: null" in floor
    assert "Math.max(0, form.input_weight_g - form.output_weight_g)" in floor
    assert "form.output_weight_g / form.input_weight_g * 100" in floor


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


def test_floor_keeps_traceability_and_formulation_but_progressively_discloses_them():
    floor = read("frontend/src/pages/ExtractionOperatorWorkspace.tsx")

    assert "More details / traceability" in floor
    assert "METRC stage input ID" in floor
    assert "METRC stage output ID" in floor
    assert "Intermediate product type" in floor
    assert "Final product type" in floor
    assert "Calculated terpene addition" in floor
    assert "Expected formulated mass" in floor


def test_backend_remains_authoritative_for_deterministic_stage_loss():
    repository = read("modules/extraction/repository.py")

    assert "if loss_weight_g is None and in_weight is not None and out_weight is not None:" in repository
    assert "loss = max(0.0, in_weight - out_weight)" in repository
    assert '"yield_pct": yield_pct' in repository
