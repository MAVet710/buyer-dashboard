import pandas as pd

from views.extraction_perfect_view_v2 import PRODUCT_TYPE_OPTIONS, _filtered_frames


EXPECTED_PRODUCT_TYPES = [
    "Sugar",
    "Badder / Batter",
    "Shatter",
    "Sauce",
    "Diamonds (THCa Diamonds)",
    "Live Resin",
    "Live Rosin",
    "Cured Resin",
    "Fresh Press (Rosin)",
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
    "HTFSE (High Terpene Full Spectrum Extract)",
    "HCFSE (High Cannabinoid Full Spectrum Extract)",
    "THCa Isolate",
    "CBD Isolate",
    "Full Spectrum Oil",
    "Broad Spectrum Oil",
    "Caviar / Moon Rocks",
    "Infused Pre-Roll (concentrate output)",
    "Vape Cart Oil",
    "Dab-ready Concentrate",
    "Other",
]


def test_product_type_options_match_required_comprehensive_list():
    assert PRODUCT_TYPE_OPTIONS == EXPECTED_PRODUCT_TYPES


def test_filtered_frames_supports_strain_filter_for_runs_and_jobs():
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
    assert len(filtered_jobs) == 1
    assert filtered_jobs.iloc[0]["strain"] == "Night Tonic"
