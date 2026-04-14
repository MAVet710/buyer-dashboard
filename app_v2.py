import streamlit as st

from ui_theme import load_modern_theme
from views.command_center import render_command_center


st.set_page_config(page_title="DoobieLogic Buyer Dashboard", layout="wide")

# Apply upgraded UI theme
st.markdown(load_modern_theme(), unsafe_allow_html=True)


st.title("DoobieLogic — Buyer & Extraction Intelligence")
st.caption("Commercial-ready modular shell (Doobie-only AI routing)")


# Sidebar Navigation
page = st.sidebar.radio(
    "Workspace",
    [
        "Command Center",
        "Legacy App (Uploads)",
    ],
)


if page == "Command Center":
    render_command_center()

elif page == "Legacy App (Uploads)":
    st.warning("This opens the original monolithic app for uploads and prep. It still contains legacy AI paths until migration is complete.")
    st.markdown("Run your existing `app.py` separately for now, then return here for intelligence.")
