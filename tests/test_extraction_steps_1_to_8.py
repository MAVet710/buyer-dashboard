import pytest

from modules.extraction.workflows import (
    EXTRACTION_WORKFLOW_TEMPLATES,
    TERPENE_HANDLING_MODES,
    calculate_final_output_g,
    calculate_terpene_weight_g,
    default_workflow_for_method,
    get_extraction_workflow,
    method_aware_stage_fields,
    validate_terpene_percentage,
)


def test_method_specific_workflow_templates_cover_major_extraction_families():
    assert set(EXTRACTION_WORKFLOW_TEMPLATES) == {
        "Hydrocarbon",
        "Ethanol",
        "CO2",
        "Ice Water Hash",
        "Dry Sift",
        "Rosin",
    }
    assert "Formulation" in EXTRACTION_WORKFLOW_TEMPLATES["Hydrocarbon"]
    assert "Distillation" in EXTRACTION_WORKFLOW_TEMPLATES["Ethanol"]
    assert "Bag Separation" in EXTRACTION_WORKFLOW_TEMPLATES["Ice Water Hash"]
    assert "Screening / Sifting" in EXTRACTION_WORKFLOW_TEMPLATES["Dry Sift"]
    assert "Curing / Jar Tech" in EXTRACTION_WORKFLOW_TEMPLATES["Rosin"]


def test_durable_workflows_branch_by_method_and_preserve_existing_keys():
    assert default_workflow_for_method("BHO").key in {"bho_live_resin", "bho_cured"}
    assert default_workflow_for_method("Ethanol").key == "ethanol_crude"
    assert default_workflow_for_method("CO2").key == "co2_extract"
    assert default_workflow_for_method("Ice Water Hash").key == "ice_water_hash"
    assert default_workflow_for_method("Dry Sift").key == "dry_sift"
    assert default_workflow_for_method("Rosin").key == "hash_rosin"

    live = get_extraction_workflow("bho_live_resin")
    assert live.has_stage("separation_crystallization")
    assert live.stage("separation_crystallization").optional is True
    assert live.has_stage("formulation")


def test_method_aware_stage_fields_are_relevant_not_global():
    assert method_aware_stage_fields("BHO") == (
        "extraction_output_g",
        "purge_output_g",
        "crystallization_output_g",
        "sauce_fraction_g",
        "diamond_fraction_g",
    )
    assert "distillate_output_g" in method_aware_stage_fields("Ethanol")
    assert "distillate_output_g" in method_aware_stage_fields("CO2")
    assert method_aware_stage_fields("Dry Sift") == ("sift_output_g", "rosin_output_g")
    assert method_aware_stage_fields("Rosin") == ("rosin_output_g",)


def test_terpene_handling_is_optional_calculated_and_overridable():
    assert TERPENE_HANDLING_MODES[0] == "Native / No Add-Back"
    assert calculate_terpene_weight_g(1000, 5) == pytest.approx(50)
    assert calculate_terpene_weight_g(1000, 5, 42) == pytest.approx(42)
    assert calculate_terpene_weight_g(1000, None, None) == 0
    assert validate_terpene_percentage(0) == 0
    with pytest.raises(ValueError, match="outside the supported formulation range"):
        validate_terpene_percentage(25)
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_terpene_weight_g(1000, 5, -1)


def test_final_output_uses_last_real_stage_when_formulation_not_used():
    result = calculate_final_output_g(
        "ethanol_crude",
        {
            "crude_output_g": 800,
            "winterized_output_g": 720,
            "filtered_output_g": 690,
            "decarbed_output_g": 670,
            "distillate_output_g": 610,
        },
        formulation_used=False,
        terpene_weight_g=30,
    )
    assert result == pytest.approx(610)


def test_final_output_adds_formulation_mass_only_when_formulation_is_used():
    formulated = calculate_final_output_g(
        "ethanol_crude",
        {"distillate_output_g": 600},
        formulation_used=True,
        formulation_base_g=600,
        terpene_weight_g=30,
    )
    native = calculate_final_output_g(
        "ethanol_crude",
        {"distillate_output_g": 600},
        formulation_used=False,
        formulation_base_g=600,
        terpene_weight_g=30,
    )
    assert formulated == pytest.approx(630)
    assert native == pytest.approx(600)


def test_measured_post_formulation_output_prevents_double_counting_terpenes():
    result = calculate_final_output_g(
        "rosin_vape",
        {"packaging": 505},
        formulation_used=True,
        formulation_base_g=480,
        terpene_weight_g=25,
    )
    assert result == pytest.approx(505)


def test_explicit_finished_output_remains_backward_compatible():
    assert calculate_final_output_g(
        "bho_cured",
        {"purge_output_g": 420},
        formulation_used=True,
        formulation_base_g=420,
        terpene_weight_g=20,
        explicit_finished_output_g=399,
    ) == pytest.approx(399)
