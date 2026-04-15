import pandas as pd
import streamlit as st

from ui.components import render_section_header, render_metric_card
from core.session_keys import INV_RAW, SALES_RAW, BUYER_READY


def _read_tabular(uploaded_file):
    name = str(getattr(uploaded_file, "name", "")).lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)


def _prepare_buyer_dataset(inv_df: pd.DataFrame, sales_df: pd.DataFrame) -> pd.DataFrame:
    if inv_df is None or sales_df is None:
        return pd.DataFrame()
    df = inv_df.copy()
    if "product_name" in df.columns and "product_name" in sales_df.columns:
        return df.merge(sales_df, on="product_name", how="left", suffixes=("_inv", "_sales"))
    return df


def render_inventory_view_v2():
    render_section_header("Inventory and Sales Upload", "CSV and Excel are both supported for buyer preparation.")

    col1, col2 = st.columns(2)
    with col1:
        inv_file = st.file_uploader("Upload Inventory File", type=["csv", "xlsx", "xls"], key="inv_upload_v2")
        if inv_file:
            inv_df = _read_tabular(inv_file)
            st.session_state[INV_RAW] = inv_df
            st.success(f"Inventory loaded: {getattr(inv_file, 'name', 'file')}")
    with col2:
        sales_file = st.file_uploader("Upload Sales File", type=["csv", "xlsx", "xls"], key="sales_upload_v2")
        if sales_file:
            sales_df = _read_tabular(sales_file)
            st.session_state[SALES_RAW] = sales_df
            st.success(f"Sales loaded: {getattr(sales_file, 'name', 'file')}")

    inv_df = st.session_state.get(INV_RAW)
    sales_df = st.session_state.get(SALES_RAW)

    stats = st.columns(2)
    with stats[0]:
        render_metric_card("Inventory Rows", len(inv_df) if isinstance(inv_df, pd.DataFrame) else 0)
    with stats[1]:
        render_metric_card("Sales Rows", len(sales_df) if isinstance(sales_df, pd.DataFrame) else 0)

    if st.button("Prepare Buyer Dataset", key="prepare_buyer_v2"):
        prepared = _prepare_buyer_dataset(inv_df, sales_df)
        st.session_state[BUYER_READY] = prepared
        st.success("Buyer dataset prepared for Doobie")

    if isinstance(inv_df, pd.DataFrame):
        st.subheader("Inventory Preview")
        st.dataframe(inv_df.head(50), use_container_width=True)
    if isinstance(sales_df, pd.DataFrame):
        st.subheader("Sales Preview")
        st.dataframe(sales_df.head(50), use_container_width=True)
