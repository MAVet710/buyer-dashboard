import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import re
from datetime import datetime

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

st.title("🌿 Cannabis Buyer Dashboard")
st.markdown("Streamlined purchasing visibility powered by Dutchie data.\n")

st.sidebar.header("🔐 Login")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
is_admin = username == "God" and password == "Major420"
trial_key = st.sidebar.text_input("Trial Access Key")
access_granted = is_admin or trial_key == "letmein"

if access_granted:
    st.sidebar.header("📂 Upload Reports")
    inv_file = st.sidebar.file_uploader("Inventory CSV", type="csv")
    sales_file = st.sidebar.file_uploader("Detailed Sales Breakdown by Product", type="xlsx")
    product_sales_file = st.sidebar.file_uploader("Product Sales Report", type="xlsx")
    aging_file = st.sidebar.file_uploader("Inventory Aging Report", type="xlsx")

    doh_threshold = st.sidebar.number_input("Days on Hand Threshold", min_value=1, max_value=30, value=21)
    velocity_adjustment = st.sidebar.number_input("Velocity Adjustment (e.g. 0.5 for slower stores)", min_value=0.01, max_value=5.0, value=0.5, step=0.01)
    filter_state = st.session_state.setdefault("metric_filter", "None")

    tabs = st.tabs(["📈 Forecast Dashboard", "📋 PO Generator"])

    with tabs[0]:
        if inv_file and product_sales_file:
            try:
                inv_df = pd.read_csv(inv_file)
                inv_df.columns = inv_df.columns.str.strip().str.lower()
                inv_df = inv_df.rename(columns={"product": "itemname", "category": "subcategory", "available": "onhandunits"})
                inv_df["onhandunits"] = pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0)
                inv_df["subcategory"] = inv_df["subcategory"].str.strip().str.lower()

                def extract_size(name):
                    name = str(name).lower()
                    if any(x in name for x in ["28g", "1oz", "1 oz"]):
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

                agg = sales_df.groupby(["mastercategory", "packagesize"]).agg({"unitssold": "sum"}).reset_index()
                agg["avgunitsperday"] = agg["unitssold"].astype(float) / date_diff * velocity_adjustment

                detail = pd.merge(inventory_summary, agg, left_on=["subcategory", "packagesize"], right_on=["mastercategory", "packagesize"], how="outer").fillna(0)
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

                if st.session_state.metric_filter == "Watchlist":
                    detail = detail[detail["reorderpriority"] == "2 – Watch Closely"]
                elif st.session_state.metric_filter == "Reorder ASAP":
                    detail = detail[detail["reorderpriority"] == "1 – Reorder ASAP"]

                st.markdown("### Inventory Forecast Table")
                for cat, group in detail.groupby("subcategory"):
                    avg_doh = int(np.floor(group["daysonhand"].mean()))
                    with st.expander(f"{cat.title()} – Avg Days On Hand: {avg_doh}"):
                        styled_cat_df = group.style.applymap(lambda val: "color: #FF3131; font-weight: bold;" if int(val) < doh_threshold else "", subset=["daysonhand"])
                        st.dataframe(styled_cat_df, use_container_width=True)

                csv = detail.to_csv(index=False).encode("utf-8")
                st.download_button("Download CSV", csv, "buyer_forecast.csv", "text/csv")

            except Exception as e:
                st.error(f"Error processing files: {e}")
        else:
            st.info("Please upload inventory and sales files to continue.")

    with tabs[1]:
        st.subheader("✏️ Purchase Order Generator")
        po_date = st.date_input("PO Date", value=datetime.today())
        vendor = st.text_input("Vendor")
        buyer = st.text_input("Buyer")
        note = st.text_area("Additional Notes")

        po_items = st.text_area("Enter PO Items (one per line, format: Product – Qty)")
        if st.button("Generate PO"):
            po_lines = po_items.strip().split("\n")
            po_data = [(line.split("–")[0].strip(), line.split("–")[1].strip()) for line in po_lines if "–" in line]
            po_df = pd.DataFrame(po_data, columns=["Product", "Quantity"])

            st.markdown(f"### PO Summary for {vendor}")
            st.markdown(f"**Date:** {po_date}  |  **Buyer:** {buyer}")
            if note:
                st.markdown(f"**Notes:** {note}")
            st.dataframe(po_df, use_container_width=True)
            csv = po_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download PO CSV", csv, "purchase_order.csv", "text/csv")

else:
    st.warning("Please log in with valid credentials or provide a trial access key.")
