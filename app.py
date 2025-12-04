import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re
from datetime import datetime

# =========================
# CONFIG & BRANDING
# =========================
CLIENT_NAME = "MAVet710"
APP_TITLE = f"{CLIENT_NAME} Purchasing Dashboard"
APP_TAGLINE = "Streamlined purchasing visibility powered by Dutchie data."
LICENSE_FOOTER = f"Licensed exclusively to {CLIENT_NAME} • Powered by MAVet710 Analytics"

background_url = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"
page_icon_url = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/IMG_7158.PNG"

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
# PASSWORD PROTECTION
# =========================
PASSWORD = "purchasing123"
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password_input = st.text_input("Enter dashboard password", type="password")
    if password_input == PASSWORD:
        st.session_state.authenticated = True
        st.experimental_rerun()
    else:
        st.stop()

# =========================
# HEADER
# =========================
st.title(f"🌿 {APP_TITLE}")
st.markdown(f"**Client:** {CLIENT_NAME}")
st.markdown(APP_TAGLINE)
st.markdown("---")

# =========================
# FILE UPLOAD
# =========================
with st.sidebar.expander("📂 Upload Reports", expanded=False):
    inv_file = st.file_uploader("Inventory CSV", type="csv")
    sales_file = st.file_uploader("Detailed Sales Breakdown by Product (optional)", type="xlsx")
    product_sales_file = st.file_uploader("Product Sales Report", type="xlsx")
    aging_file = st.file_uploader("Inventory Aging Report (optional)", type="xlsx")

doh_threshold = st.sidebar.number_input("Days on Hand Threshold", min_value=1, max_value=30, value=21)
velocity_adjustment = st.sidebar.number_input("Velocity Adjustment (e.g. 0.5 for slower stores)", min_value=0.01, max_value=5.0, value=0.5, step=0.01)
filter_state = st.session_state.setdefault("metric_filter", "None")
date_diff = st.sidebar.slider("Days in Sales Period", min_value=7, max_value=90, value=60)

# =========================
# HELPER FUNCTIONS
# =========================
def extract_strain_type(name: str, subcat: str) -> str:
    s = str(name).lower()
    c = str(subcat).lower()
    base_type = "unspecified"
    if "indica" in s:
        base_type = "indica"
    elif "sativa" in s:
        base_type = "sativa"
    elif "hybrid" in s:
        base_type = "hybrid"
    elif "cbd" in s:
        base_type = "cbd"
    is_vape_context = any(kw in s or kw in c for kw in ["vape", "cart", "pen"])
    is_preroll_context = any(kw in s or kw in c for kw in ["pre roll", "joint"])
    if ("disposable" in s) and is_vape_context:
        return f"{base_type} disposable" if base_type != "unspecified" else "disposable"
    if "infused" in s and is_preroll_context:
        return f"{base_type} infused" if base_type != "unspecified" else "infused"
    return base_type

def extract_size(text, context=None):
    s = str(text).lower()
    c = str(context).lower() if context else s
    mg = re.search(r"(\d+(\.\d+)?\s?mg)", s)
    if mg:
        return mg.group(1).replace(" ", "")
    g = re.search(r"((?:\d+\.?\d*|\.\d+)\s?g|1\s?oz|28g)", s)
    if g:
        return g.group(1).replace(" ", "")
    if any(kw in s or kw in c for kw in ["vape", "cart"]):
        half = re.search(r"\b0\.5\b|\b\.5\b", s)
        if half:
            return "0.5g"
    return "unspecified"

# =========================
# MAIN DATA LOGIC
# =========================
if inv_file and product_sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower()
        inv_df = inv_df.rename(columns={"product": "itemname", "category": "subcategory", "available": "onhandunits"})
        inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)
        inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()
        inv_df["strain_type"] = inv_df.apply(lambda row: extract_strain_type(row["itemname"], row["subcategory"]), axis=1)
        inv_df["packagesize"] = inv_df.apply(lambda row: extract_size(row["itemname"], row["subcategory"]), axis=1)
        inv_df["subcat_group"] = inv_df["subcategory"] + " – " + inv_df["packagesize"]
        inv_df = inv_df[["itemname", "strain_type", "packagesize", "subcategory", "subcat_group", "onhandunits"]]

        sales_raw = pd.read_excel(product_sales_file)
        sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()
        if "mastercategory" not in sales_raw.columns and "category" in sales_raw.columns:
            sales_raw = sales_raw.rename(columns={"category": "mastercategory"})

        product_cols = ["product", "product name", "item", "name"]
        name_col = next((c for c in product_cols if c in sales_raw.columns), None)
        sales_raw["product_name"] = sales_raw[name_col].astype(str)

        if "unitssold" not in sales_raw.columns:
            qty_cols = ["quantity sold", "qty sold", "units"]
            qty_col = next((c for c in qty_cols if c in sales_raw.columns), None)
            sales_raw["unitssold"] = sales_raw[qty_col] if qty_col else 0

        sales_df = sales_raw[sales_raw["mastercategory"].notna()].copy()
        sales_df["mastercategory"] = sales_df["mastercategory"].astype(str).str.strip().str.lower()
        sales_df = sales_df[~sales_df["mastercategory"].str.contains("accessor")]
        sales_df = sales_df[sales_df["mastercategory"] != "all"]
        sales_df["packagesize"] = sales_df.apply(lambda row: extract_size(row["product_name"], row["mastercategory"]), axis=1)
        sales_df["unitssold"] = pd.to_numeric(sales_df.get("unitssold", 0), errors="coerce").fillna(0)

        inventory_summary = inv_df.groupby(["subcategory", "strain_type", "packagesize"])["onhandunits"].sum().reset_index()
        agg = sales_df.groupby(["mastercategory", "packagesize"]).agg({"unitssold": "sum"}).reset_index()
        agg["avgunitsperday"] = agg["unitssold"].astype(float) / date_diff * velocity_adjustment

        detail = pd.merge(inventory_summary, agg, left_on=["subcategory", "packagesize"], right_on=["mastercategory", "packagesize"], how="left")
        detail["unitssold"] = pd.to_numeric(detail.get("unitssold", 0), errors="coerce").fillna(0)
        detail["avgunitsperday"] = pd.to_numeric(detail.get("avgunitsperday", 0), errors="coerce").fillna(0)
        detail["daysonhand"] = np.where(detail["avgunitsperday"] > 0, detail["onhandunits"] / detail["avgunitsperday"], np.nan)
        detail["daysonhand"] = detail["daysonhand"].replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
        detail["reorderqty"] = np.where(detail["daysonhand"] < doh_threshold, np.ceil((doh_threshold - detail["daysonhand"]) * detail["avgunitsperday"]).astype(int), 0)

        def reorder_tag(row):
            if row["daysonhand"] <= 7: return "1 – Reorder ASAP"
            if row["daysonhand"] <= 21: return "2 – Watch Closely"
            if row["avgunitsperday"] == 0: return "4 – Dead Item"
            return "3 – Comfortable Cover"

        detail["reorderpriority"] = detail.apply(reorder_tag, axis=1)
        
        # =========================
        # CATEGORY FILTER
        # =========================
        all_cats = sorted(detail["subcategory"].unique())
        default_cats = [c for c in all_cats if "accessor" not in c]
        if not default_cats:
            default_cats = all_cats

        st.sidebar.markdown("---")
        st.sidebar.header("🔎 Category Filter")
        selected_cats = st.sidebar.multiselect("Visible Product Categories", options=all_cats, default=default_cats)

        if selected_cats:
            detail = detail[detail["subcategory"].isin(selected_cats)]
            sales_for_metrics = sales_df[sales_df["mastercategory"].isin(selected_cats)]
        else:
            sales_for_metrics = sales_df.copy()

        # =========================
        # METRICS & FILTER BUTTONS
        # =========================
        total_units = int(sales_for_metrics["unitssold"].sum())
        active_categories = detail["subcategory"].nunique()
        reorder_asap = (detail["reorderpriority"] == "1 – Reorder ASAP").sum()
        watchlist_items = (detail["reorderpriority"] == "2 – Watch Closely").sum()

        c1, c2, c3, c4 = st.columns(4)
        if c1.button(f"Total Units Sold: {total_units:,}"):
            st.session_state.metric_filter = "None"
        if c2.button(f"Active Subcategories: {active_categories}"):
            st.session_state.metric_filter = "None"
        if c3.button(f"Watchlist Items: {watchlist_items}"):
            st.session_state.metric_filter = "Watchlist"
        if c4.button(f"Reorder ASAP: {reorder_asap}"):
            st.session_state.metric_filter = "Reorder ASAP"

        st.markdown("### 🧮 Inventory Forecast by Subcategory")

        detail_view = detail.copy()
        if st.session_state.metric_filter == "Watchlist":
            detail_view = detail_view[detail_view["reorderpriority"] == "2 – Watch Closely"]
        elif st.session_state.metric_filter == "Reorder ASAP":
            detail_view = detail_view[detail_view["reorderpriority"] == "1 – Reorder ASAP"]

        def highlight_low_days(val):
            try:
                val = int(val)
                return "color: #FF3131; font-weight: bold;" if val < doh_threshold else ""
            except:
                return ""

        for cat, group in detail_view.groupby("subcategory"):
            avg_doh = int(np.floor(group["daysonhand"].mean()))
            with st.expander(f"{cat.title()} – Avg Days On Hand: {avg_doh}"):
                styled_cat_df = group.style.applymap(highlight_low_days, subset=["daysonhand"])
                st.dataframe(styled_cat_df, use_container_width=True)

        csv = detail.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv, "mavet_forecast.csv", "text/csv")

    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Please upload inventory and sales files to continue.")

st.markdown("---")
year = datetime.now().year
st.markdown(f'<div class="footer">{LICENSE_FOOTER} • © {year}</div>', unsafe_allow_html=True)
