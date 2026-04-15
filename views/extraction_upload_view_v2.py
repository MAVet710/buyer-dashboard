import pandas as pd
import streamlit as st

from ui.components import render_section_header, render_metric_card
from core.session_keys import EXTRACTION_RUNS


def _read_tabular(uploaded_file):
    name = str(getattr(uploaded_file, "name", "")).lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)


def render_extraction_upload_view_v2():
    render_section_header("Extraction Upload", "CSV and Excel are supported for extraction run logs.")

    run_file = st.file_uploader(
        "Upload Extraction Runs File",
        type=["csv", "xlsx", "xls"],
        key="run_upload_v2",
    )

    if run_file:
        run_df = _read_tabular(run_file)
        st.session_state[EXTRACTION_RUNS] = run_df
        st.success(f"Extraction runs loaded: {getattr(run_file, 'name', 'file')}")

    run_df = st.session_state.get(EXTRACTION_RUNS)
    render_metric_card("Runs Loaded", len(run_df) if isinstance(run_df, pd.DataFrame) else 0)

    if isinstance(run_df, pd.DataFrame):
        st.subheader("Run Log Preview")
        st.dataframe(run_df.head(50), use_container_width=True, hide_index=True)
