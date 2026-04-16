import py_compile
from pathlib import Path

import pandas as pd

from views.extraction_perfect_view_v2 import (
    PRODUCT_TYPE_OPTIONS,
    _compute_health_score,
    _filtered_frames,
)


EXPECTED_PRODUCT_TYPES = [
    "Sugar",
    "Badder / Batter",
    "Shatter",
    "Sauce",
    "Diamonds (THCa)",
    "Live Resin",
    "Live Rosin",
    "Cured Resin",
    "Fresh Press",
    "Rosin Jam",
    "Hash Rosin",
    "Bubble Hash / Ice Water Hash",
    "Dry Sift / Kief",
    "Distillate",
    "Crude Oil",
    "RSO (Rick Simpson Oil)",
    "Tincture",
    "Wax",
    "Crumble",
    "Pull-and-Snap",
    "Terp Sauce",
    "HTFSE",
    "HCFSE",
    "THCa Isolate",
    "CBD Isolate",
    "Full Spectrum Oil",
    "Broad Spectrum Oil",
    "Caviar / Moon Rocks",
    "Infused Pre-Roll",
    "Vape Cart Oil",
    "Dab-ready Concentrate",
    "Other",
]


def test_extraction_perfect_view_v2_compiles_without_syntax_errors():
    view_path = Path(__file__).resolve().parents[1] / "views" / "extraction_perfect_view_v2.py"
    py_compile.compile(str(view_path), doraise=True)


def test_compute_health_score_bounds_and_penalties():
    assert _compute_health_score(alert_count=0, avg_yield=18.0, qa_holds=0, at_risk_batches=0) == 100.0
    assert _compute_health_score(alert_count=30, avg_yield=4.0, qa_holds=10, at_risk_batches=10) == 0.0


def test_compute_health_score_intermediate_penalties():
    assert _compute_health_score(alert_count=2, avg_yield=15.0, qa_holds=0, at_risk_batches=0) == 84.0
    assert _compute_health_score(alert_count=0, avg_yield=15.0, qa_holds=1, at_risk_batches=0) == 88.0
    assert _compute_health_score(alert_count=0, avg_yield=14.0, qa_holds=0, at_risk_batches=1) == 92.0


def test_product_type_options_match_required_comprehensive_list():
    assert PRODUCT_TYPE_OPTIONS == EXPECTED_PRODUCT_TYPES


def test_filtered_frames_supports_strain_filter_for_runs():
    run_df = pd.DataFrame(
        [
            {"state": "MA", "method": "BHO", "strain": "The 4th Kind", "toll_processing": False},
            {"state": "MA", "method": "BHO", "strain": "Night Tonic", "toll_processing": True},
        ]
    )
    job_df = pd.DataFrame(
        [
            {"state": "MA", "method": "BHO", "strain": "The 4th Kind"},
            {"state": "MA", "method": "BHO", "strain": "Night Tonic"},
        ]
    )

    filtered_runs, filtered_jobs = _filtered_frames(
        run_df,
        job_df,
        selected_state="All",
        selected_method="All",
        toll_only=False,
        selected_strain="Night Tonic",
    )

    assert len(filtered_runs) == 1
    assert filtered_runs.iloc[0]["strain"] == "Night Tonic"
    assert len(filtered_jobs) == 2
