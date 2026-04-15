import streamlit as st

from ui_theme_v2 import load_professional_theme
from ui_branding import brand_header_html, FAVICON_URL
from auth_simple import simple_auth_gate

from views.command_center_v2 import render_command_center_v2
from views.buyer_perfect_view import render_buyer_perfect_view
from views.extraction_perfect_view_v5 import render_extraction_perfect_view_v5

st.set_page_config(page_title="DoobieLogic Platform", layout="wide", page_icon=FAVICON_URL)

st.markdown(load_professional_theme(), unsafe_allow_html=True)

# ---------------- LOGIN GATE ----------------
if not simple_auth_gate():
    st.stop()

# ---------------- APP CONTENT ----------------
st.markdown(brand_header_html(), unsafe_allow_html=True)

page = st.sidebar.radio(
    "Workspace",
    ["Command Center", "Buyer Dashboard", "Extraction Command Center"],
)

if page == "Command Center":
    render_command_center_v2()

elif page == "Buyer Dashboard":
    render_buyer_perfect_view()

elif page == "Extraction Command Center":
    render_extraction_perfect_view_v5()
