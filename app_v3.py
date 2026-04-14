import streamlit as st

from ui_theme import load_modern_theme
from views.command_center import render_command_center
from views.inventory_view import render_inventory_view
from views.extraction_upload_view import render_extraction_upload_view

st.set_page_config(page_title="DoobieLogic Platform", layout="wide")

st.markdown(load_modern_theme(), unsafe_allow_html=True)

st.title("DoobieLogic Platform")
st.caption("Commercial-ready cannabis operations intelligence")

page = st.sidebar.radio(
    "Workspace",
    [
        "Command Center",
        "Inventory Prep",
        "Extraction Prep",
    ],
)

if page == "Command Center":
    render_command_center()

elif page == "Inventory Prep":
    render_inventory_view()

elif page == "Extraction Prep":
    render_extraction_upload_view()
