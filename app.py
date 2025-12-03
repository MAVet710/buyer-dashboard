import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re

st.set_page_config(page_title="Cannabis Buyer Dashboard", layout="wide", page_icon="🌿")

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

st.sidebar.header("📂 Upload Reports")
inv_file = st.sidebar.file_uploader("Inventory CSV", type="csv")
sales_file = st.sidebar.file_uploader("Sales XLSX (30-60 days)", type=["xlsx"])
product_sales_file = st.sidebar.file_uploader("Product Sales Report (60 Days)", type=["csv", "xlsx"])
inventory_aging_file = st.sidebar.file_uploader("Inventory Aging Report", type=["csv", "xlsx"])
sold_out_file = st.sidebar.file_uploader("Sold Out Report (Optional)", type=["csv", "xlsx"])

doh_threshold = st.sidebar.number_input("Days on Hand Threshold", min_value=1, max_value=30, value=21)
velocity_adjustment = st.sidebar.number_input("Velocity Adjustment (e.g. 0.5 for slower stores)", min_value=0.01, max_value=5.0, value=0.5, step=0.01)

filter_state = st.session_state.setdefault("metric_filter", "None")

if inv_file and sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower()
        inv_df = inv_df.rename(columns={"product": "itemname", "category": "subcategory", "available": "onhandunits"})
        inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)
        inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()

        def extract_size(name, subcat):
            name = str(name).lower()
            subcat = str(subcat).lower()
            if "edible" in subcat:
                match = re.search(r"(\d+\s?mg)", name)
            else:
                match = re.search(r"(\d+\.?\d*\s?(g|oz))", name)
            return match.group(1) if match else "unspecified"

        inv_df["packagesize"] = inv_df.apply(lambda row: extract_size(row["itemname"], row["subcategory"]), axis=1)
        inv_df["subcat_group"] = inv_df["subcategory"] + " – " + inv_df["packagesize"]
        inv_df = inv_df[["itemname", "packagesize", "subcategory", "subcat_group", "onhandunits"]]

        sales_raw = pd.read_excel(sales_file, header=3)
        sales_df = sales_raw[1:].copy()
        sales_df.columns = sales_raw.iloc[0]
        sales_df = sales_df.rename(columns={"Master Category": "MasterCategory", "Order Date": "OrderDate", "Net Sales": "NetSales"})
        sales_df = sales_df[sales_df["MasterCategory"].notna()].copy()
        sales_df["OrderDate"] = pd.to_datetime(sales_df["OrderDate"], errors="coerce")
        sales_df["MasterCategory"] = sales_df["MasterCategory"].str.strip().str.lower()
        sales_df = sales_df[~sales_df["MasterCategory"].str.contains("accessor")]
        sales_df = sales_df[sales_df["MasterCategory"] != "all"]

        date_range = sales_df["OrderDate"].dropna().sort_values().unique()
        date_start = st.sidebar.selectbox("Start Date", date_range)
        date_end = st.sidebar.selectbox("End Date", date_range[::-1])

        if date_start <= date_end:
            mask = (sales_df["OrderDate"] >= date_start) & (sales_df["OrderDate"] <= date_end)
            filtered_sales = sales_df[mask]
            date_diff = (pd.to_datetime(date_end) - pd.to_datetime(date_start)).days + 1

            subcat_sales = filtered_sales.groupby("MasterCategory").agg({"NetSales": "sum", "OrderDate": pd.Series.nunique}).reset_index()
            subcat_sales = subcat_sales.rename(columns={"OrderDate": "DaysSold"})
            subcat_sales["DaysSold"] = subcat_sales["DaysSold"].clip(upper=date_diff)
            subcat_sales["AvgNetSalesPerDay"] = np.where(subcat_sales["DaysSold"] > 0, (subcat_sales["NetSales"] / subcat_sales["DaysSold"]) * velocity_adjustment, 0)

            merged = pd.merge(inv_df, subcat_sales, left_on="subcategory", right_on="MasterCategory", how="left").fillna(0)
            merged["DaysOnHand"] = np.where(merged["AvgNetSalesPerDay"] > 0, merged["onhandunits"] / merged["AvgNetSalesPerDay"], np.nan)
            merged["DaysOnHand"] = merged["DaysOnHand"].replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
            merged["ReorderQty"] = np.where(merged["DaysOnHand"] < doh_threshold, np.ceil((doh_threshold - merged["DaysOnHand"]) * merged["AvgNetSalesPerDay"]).astype(int), 0)

            def reorder_tag(row):
                if row["DaysOnHand"] <= 7: return "1 – Reorder ASAP"
                if row["DaysOnHand"] <= 21: return "2 – Watch Closely"
                if row["AvgNetSalesPerDay"] == 0: return "4 – Dead Item"
                return "3 – Comfortable Cover"

            merged["ReorderPriority"] = merged.apply(reorder_tag, axis=1)
            merged = merged.sort_values(["ReorderPriority", "AvgNetSalesPerDay"], ascending=[True, False])

            total_sales = filtered_sales["NetSales"].sum()
            active_categories = merged["subcategory"].nunique()
            reorder_asap = merged[merged["ReorderPriority"] == "1 – Reorder ASAP"].shape[0]
            watchlist_items = merged[merged["ReorderPriority"] == "2 – Watch Closely"].shape[0]

            c1, c2, c3, c4 = st.columns(4)
            if c1.button(f"Total Net Sales: ${total_sales:,.2f}"): st.session_state.metric_filter = "None"
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
                merged = merged[merged["ReorderPriority"] == "2 – Watch Closely"]
            elif st.session_state.metric_filter == "Reorder ASAP":
                merged = merged[merged["ReorderPriority"] == "1 – Reorder ASAP"]

            st.markdown("### Inventory Forecast Table")
            master_categories = merged["subcategory"].unique()
            for master in sorted(master_categories):
                subset = merged[merged["subcategory"] == master]
                avg_doh = int(np.floor(subset["DaysOnHand"].mean()))
                with st.expander(f"{master.title()} – Avg Days On Hand: {avg_doh}"):
                    styled_df = subset.style.applymap(highlight_low_days, subset=["DaysOnHand"])
                    st.dataframe(styled_df, use_container_width=True)
        else:
            st.warning("Start date must be before or equal to end date.")
    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Please upload both the inventory and 30–60 day sales files to continue.")
