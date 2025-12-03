import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Cannabis Buyer Dashboard", layout="wide", page_icon="🌿")
st.markdown("""
    <style>
    body { background-color: #000; color: #fff; font-family: Arial, sans-serif; }
    .css-1d391kg { color: white; }
    </style>
""", unsafe_allow_html=True)

st.title("🍃 Cannabis Buyer Dashboard")
st.markdown("Upload Dutchie Inventory and 30-Day Sales Reports")

inv_file = st.file_uploader("Upload Inventory CSV", type="csv")
sales_file = st.file_uploader("Upload Sales XLSX", type="xlsx")

if inv_file and sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df = inv_df[["Product", "Category", "Available", "Inventory date", "Master category"]].copy()
        inv_df.columns = ["ItemName", "SubCategory", "OnHandUnits", "InventoryDate", "MasterCategory"]

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

            # Date Filter
            dates = sales_df["OrderDate"].dropna().unique()
            if len(dates) >= 2:
                start_date = st.date_input("Start Date", value=min(dates))
                end_date = st.date_input("End Date", value=max(dates))

                if start_date > end_date:
                    st.warning("Start date must be before end date")
                else:
                    mask = (sales_df["OrderDate"] >= pd.to_datetime(start_date)) & (sales_df["OrderDate"] <= pd.to_datetime(end_date))
                    filtered = sales_df[mask]

                    sales_summary = filtered.groupby("MasterCategory").agg({
                        "NetSales": "sum", "OrderDate": pd.Series.nunique
                    }).reset_index().rename(columns={"OrderDate": "DaysSold"})
                    sales_summary["AvgNetSalesPerDay"] = sales_summary["NetSales"] / sales_summary["DaysSold"]

                    inventory_summary = inv_df.groupby("MasterCategory")["OnHandUnits"].sum().reset_index()
                    df = sales_summary.merge(inventory_summary, on="MasterCategory", how="left").fillna(0)
                    df["CoverageIndex"] = df["OnHandUnits"] / df["AvgNetSalesPerDay"]

                    def reorder(row):
                        if row["CoverageIndex"] <= 7: return "1 – Reorder ASAP"
                        if row["CoverageIndex"] <= 21: return "2 – Watch Closely"
                        if row["AvgNetSalesPerDay"] == 0: return "4 – Dead Item"
                        return "3 – Comfortable Cover"

                    df["ReorderPriority"] = df.apply(reorder, axis=1)
                    df = df.sort_values(["ReorderPriority", "AvgNetSalesPerDay"], ascending=[True, False])

                    st.dataframe(df, use_container_width=True)

                    fig = px.bar(df, x="MasterCategory", y="NetSales", title="Sales by Category",
                                 color="ReorderPriority", text="OnHandUnits")
                    fig.update_layout(paper_bgcolor="black", plot_bgcolor="black", font_color="white")
                    st.plotly_chart(fig, use_container_width=True)

                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV", csv, "Buyer_View.csv", "text/csv")

    except Exception as e:
        st.error(f"Error processing files: {e}")
