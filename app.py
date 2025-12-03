import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

st.set_page_config(page_title="Cannabis Buyer Dashboard", layout="wide", page_icon="🌿")

# ---------------------- Background Styling ----------------------
background_url = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"

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
    </style>
""", unsafe_allow_html=True)

st.title("🌿 Cannabis Buyer Dashboard")
st.markdown("Streamlined purchasing visibility powered by Dutchie data.\n")

# ---------------------- SIDEBAR ----------------------
st.sidebar.header("📂 Upload Reports")
inv_file = st.sidebar.file_uploader("Inventory CSV", type="csv")
sales_file = st.sidebar.file_uploader("Sales XLSX (30-60 days)", type=["xlsx"])
product_sales_file = st.sidebar.file_uploader("Product Sales Report (60 Days)", type=["csv", "xlsx"])
inventory_aging_file = st.sidebar.file_uploader("Inventory Aging Report", type=["csv", "xlsx"])
sold_out_file = st.sidebar.file_uploader("Sold Out Report (Optional)", type=["csv", "xlsx"])

# Controls
doh_threshold = st.sidebar.number_input("Days on Hand Threshold", min_value=1, max_value=30, value=21)
velocity_adjustment = st.sidebar.number_input("Velocity Adjustment (e.g. 0.5 for slower stores)", min_value=0.01, max_value=5.0, value=0.5, step=0.01)

st.info("Reports uploaded. Processing core dashboard. Additional reports will be integrated in the next phase.")
