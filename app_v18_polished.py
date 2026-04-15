import streamlit as st

from ui_theme_v18_polish import load_v18_polished_theme
from ui_branding import brand_header_html
from auth_premium import premium_auth_gate

from views.command_center_v3 import render_command_center_v3
from views.buyer_perfect_view_v2 import render_buyer_perfect_view_v2
from views.extraction_perfect_view_v5 import render_extraction_perfect_view_v5
from views.extraction_upload_view_v2 import render_extraction_upload_view_v2
from views.inventory_view_v2 import render_inventory_view_v2
from views.inventory_automap_view import render_inventory_automap
from views.slow_movers_view import render_slow_movers_view
from views.delivery_impact_view import render_delivery_impact_view
from views.po_builder_view import render_po_builder_view
from views.learning_view import render_learning_view

st.set_page_config(page_title="DoobieLogic Platform", layout="wide")
st.markdown(load_v18_polished_theme(), unsafe_allow_html=True)

if not premium_auth_gate():
    st.stop()

# 🔥 TOP BAR (NO SIDEBAR)
st.markdown(brand_header_html(), unsafe_allow_html=True)

st.markdown('<div class="top-shell">', unsafe_allow_html=True)

# LEFT: HERO
st.markdown('''
<div class="hero-card">
  <div class="hero-kicker">DoobieLogic</div>
  <div class="hero-title">Buyer Intelligence Platform</div>
  <div class="hero-subtitle">Real-time decisions. Clean data. No guessing.</div>
</div>
''', unsafe_allow_html=True)

# RIGHT: DROPDOWN NAV
col = st.container()
with col:
    st.markdown('<div class="nav-card">', unsafe_allow_html=True)
    st.markdown('<div class="nav-label">Module</div>', unsafe_allow_html=True)

    page = st.selectbox("", [
        "Command Center",
        "Buyer Dashboard",
        "Extraction",
        "Extraction Upload",
        "Inventory",
        "Smart Upload",
        "Slow Movers",
        "Delivery Impact",
        "PO Builder",
        "Learning"
    ])

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ROUTING
if page == "Command Center":
    render_command_center_v3()
elif page == "Buyer Dashboard":
    render_buyer_perfect_view_v2()
elif page == "Extraction":
    render_extraction_perfect_view_v5()
elif page == "Extraction Upload":
    render_extraction_upload_view_v2()
elif page == "Inventory":
    render_inventory_view_v2()
elif page == "Smart Upload":
    render_inventory_automap()
elif page == "Slow Movers":
    render_slow_movers_view()
elif page == "Delivery Impact":
    render_delivery_impact_view()
elif page == "PO Builder":
    render_po_builder_view()
elif page == "Learning":
    render_learning_view()
