import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re
from datetime import datetime

# =========================
# AUTHENTICATION SETTINGS
# =========================
OWNER_CREDENTIALS = {"God": "Major420"}
TRIAL_KEYS = {"trial123", "guest420"}  # Add trial keys here

# =========================
# APP CONFIG
# =========================
CLIENT_NAME = "MAVet Purchasing Dash"
APP_TITLE = f"{CLIENT_NAME}"
LICENSE_FOOTER = f"Licensed exclusively to {CLIENT_NAME} • Powered by MAVet710 Analytics"

background_url = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"
page_icon_url = "🌿"

st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=page_icon_url)

st.markdown(f"""
    <style>
    .stApp {{
        background-image: url('{background_url}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
        color: white;
    }}
    .block-container {{
        background-color: rgba(0, 0, 0, 0.75);
        padding: 2rem;
        border-radius: 12px;
    }}
    .dataframe td {{
        color: white;
    }}
    .neon-red {{
        color: #FF3131;
        font-weight: bold;
    }}
    .stButton>button {{
        background-color: rgba(255, 255, 255, 0.1);
        color: white;
        border: 1px solid white;
    }}
    .stButton>button:hover {{
        background-color: rgba(255, 255, 255, 0.3);
    }}
    .footer {{
        text-align: center;
        font-size: 0.75rem;
        opacity: 0.7;
        margin-top: 2rem;
    }}
    </style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR AUTHENTICATION
# =========================
st.sidebar.header("🔐 Login Required")
with st.sidebar.expander("User Login", expanded=True):
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    key_access = st.text_input("Trial Key (if provided)", help="Optional access code for temporary trial use")

# Check login or trial access
authenticated = False
if username in OWNER_CREDENTIALS and password == OWNER_CREDENTIALS[username]:
    authenticated = True
elif key_access in TRIAL_KEYS:
    authenticated = True

if not authenticated:
    st.warning("Please log in with your credentials or a valid trial key to access the dashboard.")
    st.stop()

# =========================
# HEADER
# =========================
st.title("🌿 MAVet Purchasing Dashboard")
st.markdown("Streamlined purchasing visibility powered by Dutchie data.")
st.markdown("---")

# (The rest of the app logic would continue below this point: file uploaders, analysis, PO generation, etc.)
