import streamlit as st

from ui_theme_v3 import load_professional_theme
from ui_branding import brand_header_html
from auth_premium import premium_auth_gate

from views.command_center_v3 import render_command_center_v3
from views.buyer_v3 import render_buyer_perfect_view_v3
from views.extraction_perfect_view_v5 import render_extraction_perfect_view_v5
from views.extraction_upload_view_v2 import render_extraction_upload_view_v2
from views.slow_movers_view import render_slow_movers_view
from views.delivery_impact_view import render_delivery_impact_view
from views.inventory_view_v2 import render_inventory_view_v2
from views.inventory_automap_view import render_inventory_automap
from views.po_builder_view import render_po_builder_view
from views.learning_view import render_learning_view

st.set_page_config(page_title="DoobieLogic Platform", layout="wide")
st.markdown(load_professional_theme(), unsafe_allow_html=True)

if not premium_auth_gate():
    st.stop()

st.markdown(brand_header_html(), unsafe_allow_html=True)

page = st.sidebar.radio(
    "Workspace",
    [
        "Command Center",
        "Buyer Dashboard",
        "Extraction",
        "Extraction Upload",
        "Slow Movers",
        "Delivery Impact",
        "Inventory",
        "Smart Upload",
        "PO Builder",
        "Learning",
    ],
)

if page == "Command Center":
    render_command_center_v3()
elif page == "Buyer Dashboard":
    render_buyer_perfect_view_v3()
elif page == "Extraction":
    render_extraction_perfect_view_v5()
elif page == "Extraction Upload":
    render_extraction_upload_view_v2()
elif page == "Slow Movers":
    render_slow_movers_view()
elif page == "Delivery Impact":
    render_delivery_impact_view()
elif page == "Inventory":
    render_inventory_view_v2()
elif page == "Smart Upload":
    render_inventory_automap()
elif page == "PO Builder":
    render_po_builder_view()
elif page == "Learning":
    render_learning_view()
