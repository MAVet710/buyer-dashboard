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
metric_filter = st.sidebar.radio("Filter by KPI Click", ("None", "Watchlist", "Reorder ASAP"))

# ---------------------- DATA PROCESSING ----------------------
if inv_file and sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower()
        inv_df = inv_df.rename(columns={"product": "itemname", "category": "subcategory", "available": "onhandunits"})
        inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)
        inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()
        inv_df = inv_df[["itemname", "subcategory", "onhandunits"]]

        sales_raw = pd.read_excel(sales_file, header=3)
        sales_df = sales_raw[1:].copy()
        sales_df.columns = sales_raw.iloc[0]
        sales_df = sales_df.rename(columns={"Master Category": "MasterCategory", "Order Date": "OrderDate", "Net Sales": "NetSales"})
        sales_df = sales_df[sales_df["MasterCategory"].notna()].copy()
        sales_df["OrderDate"] = pd.to_datetime(sales_df["OrderDate"], errors="coerce")
        sales_df["MasterCategory"] = sales_df["MasterCategory"].str.strip().str.lower()
        sales_df = sales_df[~sales_df["MasterCategory"].str.contains("accessor")]
        sales_df = sales_df[sales_df["MasterCategory"] != "all"]

        inventory_summary = inv_df.groupby("subcategory")["onhandunits"].sum().reset_index()

        date_range = sales_df["OrderDate"].dropna().sort_values().unique()
        date_start = st.sidebar.selectbox("Start Date", date_range)
        date_end = st.sidebar.selectbox("End Date", date_range[::-1])

        if date_start <= date_end:
            mask = (sales_df["OrderDate"] >= date_start) & (sales_df["OrderDate"] <= date_end)
            filtered_sales = sales_df[mask]
            date_diff = (pd.to_datetime(date_end) - pd.to_datetime(date_start)).days + 1
            agg = filtered_sales.groupby("MasterCategory").agg({"NetSales": "sum", "OrderDate": pd.Series.nunique}).reset_index()
            agg = agg.rename(columns={"OrderDate": "DaysSold"})
            agg["DaysSold"] = agg["DaysSold"].clip(upper=date_diff)
            agg["AvgNetSalesPerDay"] = (agg["NetSales"] / agg["DaysSold"].replace(0, np.nan)) * velocity_adjustment

            df = agg.merge(inventory_summary, left_on="MasterCategory", right_on="subcategory", how="left").fillna(0)
            df["DaysOnHand"] = (df["onhandunits"] / df["AvgNetSalesPerDay"]).replace([np.inf, -np.inf], np.nan).fillna(0)
            df["DaysOnHand"] = np.floor(df["DaysOnHand"]).astype(int)
            df["ReorderQty"] = np.where(df["DaysOnHand"] < doh_threshold, np.ceil((doh_threshold - df["DaysOnHand"]) * df["AvgNetSalesPerDay"]).astype(int), 0)

            def reorder_tag(row):
                if row["DaysOnHand"] <= 7: return "1 – Reorder ASAP"
                if row["DaysOnHand"] <= 21: return "2 – Watch Closely"
                if row["AvgNetSalesPerDay"] == 0: return "4 – Dead Item"
                return "3 – Comfortable Cover"

            df["ReorderPriority"] = df.apply(reorder_tag, axis=1)
            df = df.sort_values(["ReorderPriority", "AvgNetSalesPerDay"], ascending=[True, False])

            total_sales = filtered_sales["NetSales"].sum()
            active_categories = df.shape[0]
            reorder_asap = df[df["ReorderPriority"] == "1 – Reorder ASAP"].shape[0]
            watchlist_items = df[df["ReorderPriority"] == "2 – Watch Closely"].shape[0]

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total Net Sales", f"${total_sales:,.2f}")
            kpi2.metric("Active Categories", active_categories)
            kpi3.metric("Watchlist Items", watchlist_items)
            kpi4.metric("Reorder ASAP", reorder_asap)

            def highlight_low_days(val):
                try:
                    val = int(val)
                    return "color: #FF3131; font-weight: bold;" if val < doh_threshold else ""
                except:
                    return ""

            if metric_filter == "Watchlist":
                df = df[df["ReorderPriority"] == "2 – Watch Closely"]
            elif metric_filter == "Reorder ASAP":
                df = df[df["ReorderPriority"] == "1 – Reorder ASAP"]

            styled_df = df.style.applymap(highlight_low_days, subset=["DaysOnHand"])
            st.markdown("### Inventory Forecast Table")
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.warning("Start date must be before or equal to end date.")
    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Please upload both the inventory and 30–60 day sales files to continue.")
