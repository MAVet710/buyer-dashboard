import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
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
st.markdown("Streamlined purchasing visibility powered by Dutchie data.")

st.sidebar.header("📂 Upload Reports")
inv_file = st.sidebar.file_uploader("Inventory CSV", type="csv")
sales_file = st.sidebar.file_uploader("Detailed Sales Breakdown by Product XLSX", type=["xlsx"])

# Controls
doh_threshold = st.sidebar.number_input("Days on Hand Threshold", min_value=1, max_value=30, value=21)
velocity_adjustment = st.sidebar.number_input("Velocity Adjustment", min_value=0.01, max_value=5.0, value=0.5, step=0.01)
metric_filter = st.sidebar.radio("Filter by KPI", ("None", "Watchlist", "Reorder ASAP"))

if inv_file and sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower().str.replace(" ", "")

        column_map = {
            "product": "itemname",
            "category": "mastercategory",
            "available": "onhandunits"
        }
        rename_cols = {k: v for k, v in column_map.items() if k in inv_df.columns}
        inv_df = inv_df.rename(columns=rename_cols)

        if "mastercategory" not in inv_df.columns and "category" in inv_df.columns:
            inv_df = inv_df.rename(columns={"category": "mastercategory"})

        required_cols = ["itemname", "mastercategory", "onhandunits"]
        missing_cols = [col for col in required_cols if col not in inv_df.columns]
        if missing_cols:
            st.error(f"Missing columns in inventory file: {', '.join(missing_cols)}")
            st.stop()

        def extract_package_size(name):
            name = str(name).lower()
            if 'mg' in name:
                match = re.search(r'(\d+\.?\d*)\s?mg', name)
                return match.group() if match else 'unspecified'
            else:
                match = re.search(r'(\d+\.?\d*)\s?(g|oz)', name)
                return match.group() if match else 'unspecified'

        inv_df["packagesize"] = inv_df["itemname"].apply(extract_package_size)
        inv_df["subcategory"] = inv_df["mastercategory"] + " – " + inv_df["packagesize"]

        sales_raw = pd.read_excel(sales_file, header=3)
        sales_raw.columns = sales_raw.columns.str.strip()

        if "Master Category" in sales_raw.columns:
            sales_raw = sales_raw.rename(columns={"Master Category": "MasterCategory"})
        elif "Category" in sales_raw.columns:
            sales_raw = sales_raw.rename(columns={"Category": "MasterCategory"})

        sales_raw = sales_raw.rename(columns={"Order Date": "OrderDate"})
        if "Qty Sold" in sales_raw.columns:
            sales_raw = sales_raw.rename(columns={"Qty Sold": "UnitsSold"})
        elif "Quantity Sold" in sales_raw.columns:
            sales_raw = sales_raw.rename(columns={"Quantity Sold": "UnitsSold"})

        if "MasterCategory" not in sales_raw.columns:
            st.error("Missing 'MasterCategory' or 'Category' column in sales file.")
            st.stop()

        sales_df = sales_raw[sales_raw["MasterCategory"].notna()].copy()
        sales_df["OrderDate"] = pd.to_datetime(sales_df["OrderDate"], errors="coerce")
        sales_df["MasterCategory"] = sales_df["MasterCategory"].str.lower()
        sales_df = sales_df[~sales_df["MasterCategory"].str.contains("accessor")]
        sales_df = sales_df[sales_df["MasterCategory"] != "all"]

        date_range = sales_df["OrderDate"].dropna().sort_values().unique()
        date_start = st.sidebar.selectbox("Start Date", date_range)
        date_end = st.sidebar.selectbox("End Date", date_range[::-1])

        if date_start <= date_end:
            mask = (sales_df["OrderDate"] >= date_start) & (sales_df["OrderDate"] <= date_end)
            filtered_sales = sales_df[mask].copy()
            date_diff = (pd.to_datetime(date_end) - pd.to_datetime(date_start)).days + 1

            agg = filtered_sales.groupby("MasterCategory", as_index=False).agg({"UnitsSold": "sum", "OrderDate": pd.Series.nunique})
            agg = agg.rename(columns={"OrderDate": "DaysSold"})
            agg["DaysSold"] = agg["DaysSold"].clip(upper=date_diff)
            agg["AvgUnitsPerDay"] = (agg["UnitsSold"] / agg["DaysSold"].replace(0, np.nan)) * velocity_adjustment

            inventory_summary = inv_df.groupby(["mastercategory", "subcategory"], as_index=False)["onhandunits"].sum()
            inventory_summary["onhandunits"] = pd.to_numeric(inventory_summary["onhandunits"], errors="coerce").fillna(0)

            df = pd.merge(inventory_summary, agg, left_on="mastercategory", right_on="MasterCategory", how="left")
            df["AvgUnitsPerDay"] = df["AvgUnitsPerDay"].fillna(0)
            df["DaysOnHand"] = (df["onhandunits"] / df["AvgUnitsPerDay"]).replace([np.inf, -np.inf], np.nan).fillna(0)
            df["DaysOnHand"] = np.floor(df["DaysOnHand"]).astype(int)
            df["ReorderQty"] = np.where(df["DaysOnHand"] < doh_threshold, np.ceil((doh_threshold - df["DaysOnHand"]) * df["AvgUnitsPerDay"]).astype(int), 0)

            def reorder_tag(row):
                if row["DaysOnHand"] <= 7: return "1 – Reorder ASAP"
                if row["DaysOnHand"] <= 21: return "2 – Watch Closely"
                if row["AvgUnitsPerDay"] == 0: return "4 – Dead Item"
                return "3 – Comfortable Cover"

            df["ReorderPriority"] = df.apply(reorder_tag, axis=1)

            if metric_filter == "Watchlist":
                df = df[df["ReorderPriority"] == "2 – Watch Closely"]
            elif metric_filter == "Reorder ASAP":
                df = df[df["ReorderPriority"] == "1 – Reorder ASAP"]

            total_units = filtered_sales["UnitsSold"].sum()
            active_categories = df["mastercategory"].nunique()
            reorder_asap = df[df["ReorderPriority"] == "1 – Reorder ASAP"].shape[0]
            watchlist_items = df[df["ReorderPriority"] == "2 – Watch Closely"].shape[0]

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total Units Sold", f"{total_units:,}")
            kpi2.metric("Active Categories", active_categories)
            kpi3.metric("Watchlist Items", watchlist_items)
            kpi4.metric("Reorder ASAP", reorder_asap)

            st.markdown("### Inventory Forecast by Category")
            for cat in df["mastercategory"].drop_duplicates():
                sub_df = df[df["mastercategory"] == cat].copy()
                avg_days = int(np.floor(sub_df["DaysOnHand"].mean()))
                with st.expander(f"{cat.title()} – Avg Days On Hand: {avg_days}"):
                    styled = sub_df.style.applymap(
                        lambda v: "color:#FF3131;font-weight:bold" if isinstance(v, (int, float)) and v < doh_threshold else "",
                        subset=["DaysOnHand"]
                    )
                    st.dataframe(styled, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "buyer_forecast.csv", "text/csv")

        else:
            st.warning("Start date must be before or equal to end date.")

    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Please upload both inventory and sales files.")
