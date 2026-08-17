from pathlib import Path

import pandas as pd

from services.agent_registry import PROFILES
from services.extraction_agent import (
    EXTRACTION_SPECIALIST_INSTRUCTIONS,
    build_extraction_derived_datasets,
    extraction_method_scope_frame,
    extraction_reference_index_frame,
)
from services.gemini_agent import datasets_from_session


def _runs():
    return pd.DataFrame(
        [
            {
                "run_date": "2026-08-01",
                "batch_id_internal": "RUN-BHO-1",
                "method": "BHO",
                "input_weight_g": 1000,
                "intermediate_output_g": 220,
                "finished_output_g": 180,
                "residual_loss_g": 780,
                "yield_pct": 18.0,
                "post_process_efficiency_pct": 81.8,
                "status": "Complete",
                "coa_status": "Passed",
                "qa_hold": False,
                "est_revenue_usd": 3600,
                "cogs_usd": 1800,
            },
            {
                "run_date": "2026-08-02",
                "batch_id_internal": "RUN-ROSIN-1",
                "method": "Rosin",
                "input_weight_g": 800,
                "intermediate_output_g": 210,
                "finished_output_g": 190,
                "residual_loss_g": 590,
                "yield_pct": 23.75,
                "post_process_efficiency_pct": 90.5,
                "status": "Complete",
                "coa_status": "Passed",
                "qa_hold": False,
                "est_revenue_usd": 4300,
                "cogs_usd": 2200,
            },
            {
                "run_date": "2026-08-03",
                "batch_id_internal": "RUN-BHO-HOLD",
                "method": "BHO",
                "input_weight_g": 1000,
                "intermediate_output_g": 180,
                "finished_output_g": 130,
                "residual_loss_g": 820,
                "yield_pct": 13.0,
                "post_process_efficiency_pct": 72.2,
                "status": "Hold",
                "coa_status": "Not Submitted",
                "qa_hold": True,
                "est_revenue_usd": 2100,
                "cogs_usd": 1900,
            },
        ]
    )


def test_reference_index_has_requested_forum_families_and_safety_layer():
    refs = extraction_reference_index_frame()
    names = " | ".join(refs["source_name"].astype(str).tolist())
    assert "Future4200" in names
    assert "ICMag" in names
    assert "Skunk Pharm Research" in names
    assert "BeanBasement" in names
    assert "OSHA" in names


def test_method_scope_covers_major_extraction_families():
    scope = extraction_method_scope_frame()
    categories = set(scope["category"])
    assert "Hydrocarbons (BHO/PHO)" in categories
    assert "Solventless" in categories
    assert "CO2" in categories
    assert "Ethanol & Liquid Solvents" in categories
    assert "Distillation & Isolation" in categories
    assert "Emerging & Experimental" in categories
    assert "Conversion Chemistry Review" in categories


def test_derived_extraction_views_quantify_method_and_hold_risk():
    output = build_extraction_derived_datasets({"extraction_runs": _runs()})
    assert "extraction_run_analysis" in output
    assert "extraction_method_summary" in output
    assert "extraction_qa_holds" in output
    summary = output["extraction_method_summary"]
    rosin = summary.loc[summary["method"] == "Rosin"].iloc[0]
    bho = summary.loc[summary["method"] == "BHO"].iloc[0]
    assert rosin["avg_computed_yield_pct"] > bho["avg_computed_yield_pct"]
    assert int(bho["qa_hold_runs"]) == 1
    holds = output["extraction_qa_holds"]
    assert "RUN-BHO-HOLD" in set(holds["batch_id"])


def test_extraction_session_gets_source_index_and_derived_data():
    state = {"ecc_run_log": _runs()}
    datasets = datasets_from_session(state, profile=PROFILES["extraction"])
    assert "extraction_runs" in datasets
    assert "extraction_method_scope" in datasets
    assert "extraction_reference_index" in datasets
    assert "extraction_run_analysis" in datasets
    assert "extraction_method_summary" in datasets
    assert "extraction_qa_holds" in datasets
    assert "extraction_data_availability" in datasets


def test_extraction_profile_and_prompt_are_specialized_after_patch():
    profile = PROFILES["extraction"]
    assert profile.name == "Extraction Scientist Agent"
    assert "chemical/process engineer" in profile.role
    assert "hydrocarbon processing" in profile.focus
    assert "solventless" in profile.focus
    assert "process safety" in profile.focus

    source = Path("services/gemini_agent.py").read_text(encoding="utf-8")
    assert "EXTRACTION_SPECIALIST_INSTRUCTIONS" in source
    assert 'active.key == "extraction"' in source


def test_extraction_guidance_requires_real_source_text_and_safety_priority():
    instructions = EXTRACTION_SPECIALIST_INSTRUCTIONS.casefold()
    assert "never attribute a claim to a forum unless" in instructions
    assert "mawp" in instructions
    assert "pressure relief" in instructions
    assert "hazardous-location-rated equipment" in instructions
    assert "do not provide step-by-step conversion recipes" in instructions
