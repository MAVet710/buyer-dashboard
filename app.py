@@ -1,102 +1,110 @@
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Cannabis Buyer Dashboard", layout="wide", page_icon="🌿")

# ---------------------- Styling ----------------------
st.markdown("""
    <style>
    body {
    body, .stApp {
        background-color: #000;
        color: #fff;
    }
    .stApp {
        background-color: #000;
    }
    .css-1d391kg { background-color: #000 !important; }
    .css-1v0mbdj { background-color: #111 !important; border-radius: 8px; padding: 10px; }
    .metric-label { font-weight: 600; font-size: 14px; color: #ccc; }
    .metric-value { font-size: 20px; font-weight: bold; color: #fff; }
    </style>
""", unsafe_allow_html=True)

st.title("🌿 Cannabis Buyer Dashboard")
st.markdown("**Upload Dutchie Inventory and 30-Day Sales Reports**")
st.markdown("Streamlined purchasing visibility powered by Dutchie data.\n")

inv_file = st.file_uploader("Upload Inventory CSV", type="csv")
sales_file = st.file_uploader("Upload Sales XLSX", type=["xlsx"])
# ---------------------- SIDEBAR ----------------------
st.sidebar.header("📂 Upload Reports")
inv_file = st.sidebar.file_uploader("Inventory CSV", type="csv")
sales_file = st.sidebar.file_uploader("Sales XLSX (30 days)", type=["xlsx"])

# ---------------------- MAIN LOGIC ----------------------
if inv_file and sales_file:
    try:
        # --- INVENTORY ---
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower()
        rename_map = {
        inv_df = inv_df.rename(columns={
            "product": "itemname",
            "category": "subcategory",
            "available": "onhandunits"
        }
        inv_df = inv_df.rename(columns={k: v for k, v in rename_map.items() if k in inv_df.columns})
        })
        inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)

        required_cols = ["itemname", "subcategory", "onhandunits"]
        missing = [col for col in required_cols if col not in inv_df.columns]
        if missing:
            st.error(f"Missing required columns in inventory file: {missing}")
            st.stop()
        inv_df = inv_df[required_cols]
        inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()
        inv_df = inv_df[["itemname", "subcategory", "onhandunits"]]

        # --- SALES ---
        sales_raw = pd.read_excel(sales_file, header=3)
        sales_df = sales_raw[1:].copy()
        sales_df.columns = sales_raw.iloc[0]
        sales_df = sales_df.rename(columns={
            "Master Category": "MasterCategory",
            "Order Date": "OrderDate",
            "Net Sales": "NetSales"
        })
        sales_df = sales_df[sales_df["MasterCategory"].notna()].copy()
        sales_df["OrderDate"] = pd.to_datetime(sales_df["OrderDate"], errors="coerce")
        sales_df["MasterCategory"] = sales_df["MasterCategory"].str.strip().str.lower()
        sales_df = sales_df[~sales_df["MasterCategory"].str.contains("accessor")]

        inventory_summary = inv_df.groupby("subcategory")["onhandunits"].sum().reset_index()

        # --- DATE RANGE FILTER ---
        date_range = sales_df["OrderDate"].dropna().sort_values().unique()
        date_start = st.selectbox("Start Date", date_range)
        date_end = st.selectbox("End Date", date_range[::-1])
        date_start = st.sidebar.selectbox("Start Date", date_range)
        date_end = st.sidebar.selectbox("End Date", date_range[::-1])

        if date_start <= date_end:
            mask = (sales_df["OrderDate"] >= date_start) & (sales_df["OrderDate"] <= date_end)
            filtered_sales = sales_df[mask]
            agg = filtered_sales.groupby("MasterCategory").agg({
                "NetSales": "sum",
                "OrderDate": pd.Series.nunique
            }).reset_index()
            agg = agg.rename(columns={"OrderDate": "DaysSold"})
            agg["AvgNetSalesPerDay"] = agg["NetSales"] / agg["DaysSold"]

            df = agg.merge(inventory_summary, left_on="MasterCategory", right_on="subcategory", how="left").fillna(0)
            df["CoverageIndex"] = df["onhandunits"] / df["AvgNetSalesPerDay"]

            def reorder_tag(row):
                if row["CoverageIndex"] <= 7: return "1 – Reorder ASAP"
                if row["CoverageIndex"] <= 21: return "2 – Watch Closely"
                if row["AvgNetSalesPerDay"] == 0: return "4 – Dead Item"
                return "3 – Comfortable Cover"

            df["ReorderPriority"] = df.apply(reorder_tag, axis=1)
            df = df.sort_values(["ReorderPriority", "AvgNetSalesPerDay"], ascending=[True, False])

            st.markdown("_Note: Sales data is from the last 30 days. Inventory reflects today's snapshot._")
            # ---------------------- METRICS ----------------------
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Sales", f"${df['NetSales'].sum():,.0f}")
            col2.metric("Active Categories", df['MasterCategory'].nunique())
            col3.metric("Watchlist Items", (df['ReorderPriority'] == "2 – Watch Closely").sum())
            col4.metric("Reorder ASAP", (df['ReorderPriority'] == "1 – Reorder ASAP").sum())

            # ---------------------- DATA & CHART ----------------------
            st.subheader("📊 Inventory Coverage & Sales")
            st.dataframe(df, use_container_width=True)

            fig = px.bar(df, x="MasterCategory", y="NetSales", title="Sales by Category",
                         color="ReorderPriority", text="onhandunits")
            fig.update_layout(paper_bgcolor="black", plot_bgcolor="black", font_color="white")
            fig.update_layout(paper_bgcolor="#111", plot_bgcolor="#111", font_color="white")
            st.plotly_chart(fig, use_container_width=True)

            # ---------------------- EXPORT ----------------------
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Buyer View CSV", csv, "Buyer_View.csv", "text/csv", key='download-csv')
            st.download_button("📥 Download Buyer View CSV", csv, "Buyer_View.csv", "text/csv")
        else:
            st.warning("Start date must be before or equal to end date.")
    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Please upload both the inventory and 30-day sales files to continue.")
