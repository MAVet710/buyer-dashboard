import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re
from datetime import datetime

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
    </style>
""", unsafe_allow_html=True)

st.title("🌿 MAVet710 Purchasing Dashboard")
st.markdown(APP_TAGLINE)
st.markdown("---")

# Authentication and Trial Key
with st.sidebar:
    st.subheader("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    trial_key = st.text_input("Trial Key (optional)")
    login_btn = st.button("Login")

    ADMIN_LOGGED_IN = username == "God" and password == "Major420"
    TRIAL_USER = trial_key in ["trial123", "guest420"]

    if login_btn:
        if ADMIN_LOGGED_IN:
            st.success("Admin access granted.")
        elif TRIAL_USER:
            st.success("Trial access granted.")
        else:
            st.error("Invalid credentials or trial key.")

if not (ADMIN_LOGGED_IN or TRIAL_USER):
    st.warning("Please log in or enter a valid trial key to access the dashboard.")
    st.stop()

# App Tabs
main_tab, po_tab = st.tabs(["📊 Dashboard", "📦 Generate Purchase Orders"])

with main_tab:
    st.sidebar.header("📂 Upload Reports")
    inv_file = st.sidebar.file_uploader("Inventory CSV", type="csv")
    product_sales_file = st.sidebar.file_uploader("Product Sales Report", type="xlsx")

    doh_threshold = st.sidebar.number_input("Days on Hand Threshold", min_value=1, max_value=30, value=21)
    velocity_adjustment = st.sidebar.number_input("Velocity Adjustment", min_value=0.01, max_value=5.0, value=0.5, step=0.01)
    filter_state = st.session_state.setdefault("metric_filter", "None")

    if inv_file and product_sales_file:
        try:
            inv_df = pd.read_csv(inv_file)
            inv_df.columns = inv_df.columns.str.strip().str.lower()
            inv_df = inv_df.rename(columns={"product": "itemname", "category": "subcategory", "available": "onhandunits"})
            inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)
            inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()

            def extract_size(name):
                name = str(name).lower()
                if any(x in name for x in ["1oz", "1 oz", "28g"]):
                    return "1oz"
                mg_match = re.search(r"(\d+\s?mg)", name)
                g_match = re.search(r"(\d+\.?\d*\s?(g|oz))", name)
                return mg_match.group(1) if mg_match else (g_match.group(1) if g_match else "unspecified")

            inv_df["packagesize"] = inv_df["itemname"].apply(extract_size)
            inv_df["subcat_group"] = inv_df["subcategory"] + " – " + inv_df["packagesize"]
            inv_df = inv_df[["itemname", "packagesize", "subcategory", "subcat_group", "onhandunits"]]

            sales_raw = pd.read_excel(product_sales_file)
            sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()
            if "mastercategory" not in sales_raw.columns and "category" in sales_raw.columns:
                sales_raw = sales_raw.rename(columns={"category": "mastercategory"})

            sales_raw = sales_raw.rename(columns={
                "product": "product",
                "quantity sold": "unitssold",
                "weight": "packagesize"
            })

            sales_df = sales_raw[sales_raw["mastercategory"].notna()].copy()
            sales_df["mastercategory"] = sales_df["mastercategory"].str.strip().str.lower()
            sales_df = sales_df[~sales_df["mastercategory"].str.contains("accessor")]
            sales_df = sales_df[sales_df["mastercategory"] != "all"]

            inventory_summary = inv_df.groupby(["subcategory", "packagesize"])["onhandunits"].sum().reset_index()

            st.sidebar.write("Select timeframe length (in days):")
            date_diff = st.sidebar.slider("Days in Sales Period", min_value=7, max_value=90, value=60)

            agg = sales_df.groupby("mastercategory").agg({"unitssold": "sum"}).reset_index()
            agg["avgunitsperday"] = agg["unitssold"].astype(float) / date_diff * velocity_adjustment

            detail = pd.merge(inventory_summary, agg, left_on="subcategory", right_on="mastercategory", how="left").fillna(0)
            detail["daysonhand"] = np.where(detail["avgunitsperday"] > 0, detail["onhandunits"] / detail["avgunitsperday"], np.nan)
            detail["daysonhand"] = detail["daysonhand"].replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
            detail["reorderqty"] = np.where(detail["daysonhand"] < doh_threshold, np.ceil((doh_threshold - detail["daysonhand"]) * detail["avgunitsperday"]).astype(int), 0)

            def reorder_tag(row):
                if row["daysonhand"] <= 7: return "1 – Reorder ASAP"
                if row["daysonhand"] <= 21: return "2 – Watch Closely"
                if row["avgunitsperday"] == 0: return "4 – Dead Item"
                return "3 – Comfortable Cover"

            detail["reorderpriority"] = detail.apply(reorder_tag, axis=1)
            detail = detail.sort_values(["reorderpriority", "avgunitsperday"], ascending=[True, False])

            total_units = sales_df["unitssold"].astype(float).sum()
            active_categories = detail["subcategory"].nunique()
            reorder_asap = detail[detail["reorderpriority"] == "1 – Reorder ASAP"].shape[0]
            watchlist_items = detail[detail["reorderpriority"] == "2 – Watch Closely"].shape[0]

            c1, c2, c3, c4 = st.columns(4)
            if c1.button(f"Total Units Sold: {int(total_units)}"): st.session_state.metric_filter = "None"
            if c2.button(f"Active Categories: {active_categories}"): st.session_state.metric_filter = "None"
            if c3.button(f"Watchlist Items: {watchlist_items}"): st.session_state.metric_filter = "Watchlist"
            if c4.button(f"Reorder ASAP: {reorder_asap}"): st.session_state.metric_filter = "Reorder ASAP"

            def highlight_low_days(val):
                try:
                    val = int(val)
                    return "color: #FF3131; font-weight: bold;" if val < doh_threshold else ""
                except:
                    return ""

            if st.session_state.metric_filter == "Watchlist":
                detail = detail[detail["reorderpriority"] == "2 – Watch Closely"]
            elif st.session_state.metric_filter == "Reorder ASAP":
                detail = detail[detail["reorderpriority"] == "1 – Reorder ASAP"]

            st.markdown("### Inventory Forecast Table")
            master_groups = detail.groupby("subcategory")
            for cat, group in master_groups:
                avg_doh = int(np.floor(group["daysonhand"].mean()))
                with st.expander(f"{cat.title()} – Avg Days On Hand: {avg_doh}"):
                    styled_cat_df = group.style.applymap(highlight_low_days, subset=["daysonhand"])
                    st.dataframe(styled_cat_df, use_container_width=True)

            csv = detail.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "buyer_forecast.csv", "text/csv")

            # Store data for use in PO tab
            st.session_state["po_detail"] = detail

        except Exception as e:
            st.error(f"Error processing files: {e}")
    else:
        st.info("Please upload inventory and sales files to continue.")

with po_tab:
    st.subheader("📦 Purchase Order Suggestions")
    if "po_detail" in st.session_state:
        po_df = st.session_state["po_detail"]
        reorder_df = po_df[po_df["reorderqty"] > 0][["subcategory", "packagesize", "onhandunits", "avgunitsperday", "daysonhand", "reorderqty"]]
        reorder_df = reorder_df.sort_values(by="reorderqty", ascending=False)
        st.dataframe(reorder_df, use_container_width=True)

        po_csv = reorder_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Purchase Order", po_csv, "purchase_order.csv", "text/csv")
    else:
        st.info("No reorder data found. Please upload files and view dashboard first.")

st.markdown("---")
year = datetime.now().year
st.markdown(f'<div class="footer">{LICENSE_FOOTER} • © {year}</div>', unsafe_allow_html=True)
