import streamlit as st
from doobie_panels import run_extraction_doobie


def render_extraction_view(run_df):
    st.header("🧪 Extraction Command Center")

    if st.button("Generate AI Extraction Brief"):
        run_extraction_doobie(run_df)
