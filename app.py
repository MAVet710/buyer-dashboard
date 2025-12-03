import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="Cannabis Buyer Dashboard", layout="wide", page_icon="🌿")

st.markdown("""
    <style>
    body {
        background-color: #000;
        color: #fff;
    }
    .stApp {
        background-color: #000;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🌿 Cannabis Buyer Dashboard")
st.markdown("**Upload Dutchie Inventory and 30-Day Sales Reports**")

inv_file = st.file_uploader("Upload Inventory CSV", type="csv")
sales_file = st.file_uploader("Upload Sales XLSX", type=["xlsx"])

if inv_file and sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower()
        inv_df = inv_df.rename(columns={
            "product": "ItemName",
            "category": "SubCategory",
            "available": "OnHandUnits",
            "inventory date": "InventoryDate",
            "master category": "MasterCategory"
        })
        inv_df = inv_df[["ItemName", "SubCategory", "OnHandUnits", "InventoryDate", "MasterCategory"]]

        sales_raw = pd.read_excel(sales_file, header=3)
        if sales_raw.shape[0] > 1:
            sales_df = sales_raw[1:].copy()
            sales_df.columns = sales_raw.iloc[0]
            sales_df = sales_df.rename(columns={
                "Master Category": "MasterCategory",
                "Order Date": "OrderDate",
                "Net Sales": "NetSales"
            })
            sales_df = sales_df[sales_df["MasterCategory"].notna()].copy()
            sales_df["OrderDate"] = pd.to_datetime(sales_df["OrderDate"], errors='coerce')

            inventory_summary = inv_df.groupby("MasterCategory")["OnHandUnits"].sum().reset_index()

            date_range = sales_df["OrderDate"].dropna().sort_values().unique()
            date_start = st.selectbox("Start Date", date_range)
            date_end = st.selectbox("End Date", date_range[::-1])

            if date_start <= date_end:
                mask = (sales_df["OrderDate"] >= date_start) & (sales_df["OrderDate"] <= date_end)
                filtered_sales = sales_df[mask]
                agg = filtered_sales.groupby("MasterCategory").agg({
                    "NetSales": "sum",
                    "OrderDate": pd.Series.nunique
                }).reset_index()
                agg = agg.rename(columns={"OrderDate": "DaysSold"})
                agg["AvgNetSalesPerDay"] = agg["NetSales"] / agg["DaysSold"]

                df = agg.merge(inventory_summary, on="MasterCategory", how="left").fillna(0)
                df["CoverageIndex"] = df["OnHandUnits"] / df["AvgNetSalesPerDay"]

                def reorder_tag(row):
                    if row["CoverageIndex"] <= 7: return "1 – Reorder ASAP"
                    if row["CoverageIndex"] <= 21: return "2 – Watch Closely"
                    if row["AvgNetSalesPerDay"] == 0: return "4 – Dead Item"
                    return "3 – Comfortable Cover"

                df["ReorderPriority"] = df.apply(reorder_tag, axis=1)
                df = df.sort_values(["ReorderPriority", "AvgNetSalesPerDay"], ascending=[True, False])

                st.dataframe(df, use_container_width=True)

                fig = px.bar(df, x="MasterCategory", y="NetSales", title="Sales by Category",
                             color="ReorderPriority", text="OnHandUnits")
                fig.update_layout(paper_bgcolor="black", plot_bgcolor="black", font_color="white")
                st.plotly_chart(fig, use_container_width=True)

                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download Buyer View CSV", csv, "Buyer_View.csv", "text/csv", key='download-csv')
            else:
                st.warning("Start date must be before or equal to end date.")
        else:
            st.error("Sales file is empty or invalid.")
    except Exception as e:
        st.error(f"Error processing files: {e}")
