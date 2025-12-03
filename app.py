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
sales_file = st.sidebar.file_uploader("Sales XLSX (30 days)", type=["xlsx"])

# ---------------------- MAIN LOGIC ----------------------
if inv_file and sales_file:
    try:
        inv_df = pd.read_csv(inv_file)
        inv_df.columns = inv_df.columns.str.strip().str.lower()
        inv_df = inv_df.rename(columns={
            "product": "itemname",
            "category": "subcategory",
            "available": "onhandunits"
        })
        inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)
        inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()
        inv_df = inv_df[["itemname", "subcategory", "onhandunits"]]

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
        sales_df = sales_df[sales_df["MasterCategory"] != "all"]

        inventory_summary = inv_df.groupby("subcategory")["onhandunits"].sum().reset_index()

        date_range = sales_df["OrderDate"].dropna().sort_values().unique()
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
            df["DaysOnHand"] = np.floor(df["onhandunits"] / df["AvgNetSalesPerDay"]).astype(int)

            def reorder_tag(row):
                if row["DaysOnHand"] <= 7: return "1 – Reorder ASAP"
                if row["DaysOnHand"] <= 21: return "2 – Watch Closely"
                if row["AvgNetSalesPerDay"] == 0: return "4 – Dead Item"
                return "3 – Comfortable Cover"

            df["ReorderPriority"] = df.apply(reorder_tag, axis=1)
            df = df.sort_values(["ReorderPriority", "AvgNetSalesPerDay"], ascending=[True, False])

            selected_filter = st.session_state.get("selected_filter", "All")

            col1, col2, col3, col4 = st.columns(4)
            if col1.button(f"Total Sales: ${df['NetSales'].sum():,.0f}"):
                st.session_state.selected_filter = "All"
            if col2.button(f"Active Categories: {df['MasterCategory'].nunique()}"):
                st.session_state.selected_filter = "Active"
            if col3.button(f"Watchlist Items: {(df['ReorderPriority'] == '2 – Watch Closely').sum()}"):
                st.session_state.selected_filter = "Watch"
            if col4.button(f"Reorder ASAP: {(df['ReorderPriority'] == '1 – Reorder ASAP').sum()}"):
                st.session_state.selected_filter = "Reorder"

            selected_filter = st.session_state.get("selected_filter", "All")
            st.markdown(f"### Showing: {selected_filter} Categories")

            if selected_filter == "Watch":
                df = df[df["ReorderPriority"] == "2 – Watch Closely"]
            elif selected_filter == "Reorder":
                df = df[df["ReorderPriority"] == "1 – Reorder ASAP"]
            elif selected_filter == "Active":
                df = df[df["NetSales"] > 0]

            def highlight_low_days(val):
                try:
                    val = int(val)
                    return "color: #FF3131; font-weight: bold;" if val < 100 else ""
                except:
                    return ""

            styled_df = df.style.applymap(highlight_low_days, subset=["DaysOnHand"])
            st.dataframe(styled_df, use_container_width=True)

            fig = px.bar(df, x="MasterCategory", y="NetSales", title="Sales by Category",
                         color="ReorderPriority", text="onhandunits")
            fig.update_layout(paper_bgcolor="#000000", plot_bgcolor="#000000", font_color="white")
            st.plotly_chart(fig, use_container_width=True)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Buyer View CSV", csv, "Buyer_View.csv", "text/csv")
        else:
            st.warning("Start date must be before or equal to end date.")
    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Please upload both the inventory and 30-day sales files to continue.")
