import streamlit as st
from doobie_panels import run_extraction_doobie


def render_extraction_view(run_df):
    st.header("🧪 Extraction Command Center")

    st.markdown("### AI Extraction Brief")
    if st.button("Generate AI Extraction Brief", key="extraction_ai_brief_btn"):
        run_extraction_doobie(run_df)
