import streamlit as st

from ui_theme import load_modern_theme
from views.command_center import render_command_center
from views.inventory_view import render_inventory_view
from views.extraction_upload_view import render_extraction_upload_view
from views.extraction_analytics_view import render_extraction_analytics_view
from views.extraction_parity_view import render_extraction_parity_view
from views.po_builder_view import render_po_builder_view
from views.po_builder_smart import render_smart_po_builder
from views.learning_view import render_learning_view
from views.buyer_parity_view import render_buyer_parity_view

st.set_page_config(page_title="DoobieLogic Platform", layout="wide")

st.markdown(load_modern_theme(), unsafe_allow_html=True)

st.title("DoobieLogic Platform")
st.caption("Commercial-ready cannabis intelligence system")

page = st.sidebar.radio(
    "Workspace",
    [
        "Command Center",
        "Buyer Dashboard (Parity)",
        "Inventory Prep",
        "Extraction Command Center (Parity)",
        "Extraction Prep",
        "Extraction Analytics",
        "PO Builder",
        "Smart PO",
        "Learning",
    ],
)

if page == "Command Center":
    render_command_center()

elif page == "Buyer Dashboard (Parity)":
    render_buyer_parity_view()

elif page == "Inventory Prep":
    render_inventory_view()

elif page == "Extraction Command Center (Parity)":
    render_extraction_parity_view()

elif page == "Extraction Prep":
    render_extraction_upload_view()

elif page == "Extraction Analytics":
    render_extraction_analytics_view()

elif page == "PO Builder":
    render_po_builder_view()

elif page == "Smart PO":
    df = st.session_state.get("detail_product_cached_df")
    render_smart_po_builder(df)

elif page == "Learning":
    render_learning_view()
