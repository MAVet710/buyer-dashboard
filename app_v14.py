import streamlit as st

from ui_theme import load_modern_theme
from views.command_center import render_command_center
from views.buyer_perfect_view import render_buyer_perfect_view
from views.extraction_perfect_view_v5 import render_extraction_perfect_view_v5
from views.inventory_view import render_inventory_view
from views.slow_movers_view import render_slow_movers_view
from views.delivery_impact_view import render_delivery_impact_view
from views.po_builder_view import render_po_builder_view
from views.po_builder_smart import render_smart_po_builder
from views.learning_view import render_learning_view

st.set_page_config(page_title="DoobieLogic Platform", layout="wide")

st.markdown(load_modern_theme(), unsafe_allow_html=True)

st.title("DoobieLogic Platform")
st.caption("Commercial-ready cannabis intelligence system")

page = st.sidebar.radio(
    "Workspace",
    [
        "Command Center",
        "Buyer Dashboard",
        "Extraction Command Center",
        "Slow Movers",
        "Delivery Impact",
        "Inventory Prep",
        "PO Builder",
        "Smart PO",
        "Learning",
    ],
)

if page == "Command Center":
    render_command_center()

elif page == "Buyer Dashboard":
    render_buyer_perfect_view()

elif page == "Extraction Command Center":
    render_extraction_perfect_view_v5()

elif page == "Slow Movers":
    render_slow_movers_view()

elif page == "Delivery Impact":
    render_delivery_impact_view()

elif page == "Inventory Prep":
    render_inventory_view()

elif page == "PO Builder":
    render_po_builder_view()

elif page == "Smart PO":
    df = st.session_state.get("detail_product_cached_df")
    render_smart_po_builder(df)

elif page == "Learning":
    render_learning_view()
