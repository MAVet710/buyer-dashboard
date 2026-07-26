from modules.extraction_quick_entry import (
    build_quick_run_record,
    quick_stage_weight_updates,
    stage_completion_flags,
)


def test_quick_run_record_starts_at_intake_with_safe_defaults():
    record = build_quick_run_record(
        run_date="2026-07-25",
        state="MA",
        client_name="In House",
        batch_id_internal="RUN-101",
        method="BHO",
        workflow_template="Hydrocarbon",
        product_type="Live Resin",
        input_material_type="Fresh Frozen",
        input_weight_g=453.6,
    )

    assert record["batch_id_internal"] == "RUN-101"
    assert record["process_stage"] == "Intake"
    assert record["status"] == "Queued"
    assert record["input_weight_g"] == 453.6
    assert record["ready_for_transfer"] is False


def test_stage_flags_progress_to_transfer_ready():
    stages = ["Intake", "Extraction", "Formulation", "Filling / Packaging", "Final Output"]

    flags = stage_completion_flags(stages, "Final Output")

    assert flags["intake_complete"] is True
    assert flags["extraction_complete"] is True
    assert flags["formulation_complete"] is True
    assert flags["filling_complete"] is True
    assert flags["packaging_complete"] is True
    assert flags["ready_for_transfer"] is True


def test_quick_stage_weight_routes_to_mass_balance_fields():
    assert quick_stage_weight_updates("Extraction", 80.0) == {
        "extraction_output_g": 80.0,
        "intermediate_output_g": 80.0,
    }
    assert quick_stage_weight_updates("Winterization", 70.0) == {
        "post_process_output_g": 70.0,
        "intermediate_output_g": 70.0,
    }
    assert quick_stage_weight_updates("Final Output", 62.5) == {
        "final_output_g": 62.5,
        "finished_output_g": 62.5,
    }
