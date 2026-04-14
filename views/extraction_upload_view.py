import streamlit as st
import pandas as pd

from ui.components import render_section_header, render_metric_card
from core.session_keys import EXTRACTION_RUNS


def render_extraction_upload_view():
    render_section_header("Extraction Upload", "Prepare extraction data for intelligence")

    run_file = st.file_uploader("Upload Extraction Runs CSV", type=["csv"], key="run_upload")

    if run_file:
        run_df = pd.read_csv(run_file)
        st.session_state[EXTRACTION_RUNS] = run_df
        st.success("Extraction runs loaded")

    run_df = st.session_state.get(EXTRACTION_RUNS)

    render_metric_card("Runs Loaded", len(run_df) if isinstance(run_df, pd.DataFrame) else 0)

    if isinstance(run_df, pd.DataFrame):
        st.subheader("Run Log Preview")
        st.dataframe(run_df.head(50), use_container_width=True)
