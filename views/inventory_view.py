import streamlit as st
import pandas as pd

from ui.components import render_section_header, render_metric_card
from core.session_keys import INV_RAW, SALES_RAW, BUYER_READY


def _prepare_buyer_dataset(inv_df: pd.DataFrame, sales_df: pd.DataFrame) -> pd.DataFrame:
    # Simple starter logic (you can upgrade this later)
    if inv_df is None or sales_df is None:
        return pd.DataFrame()

    df = inv_df.copy()

    if "product_name" in df.columns and "product_name" in sales_df.columns:
        merged = df.merge(sales_df, on="product_name", how="left", suffixes=("_inv", "_sales"))
    else:
        merged = df

    return merged


def render_inventory_view():
    render_section_header("Inventory & Sales Upload", "Prepare data for buyer intelligence")

    col1, col2 = st.columns(2)

    with col1:
        inv_file = st.file_uploader("Upload Inventory CSV", type=["csv"], key="inv_upload")
        if inv_file:
            inv_df = pd.read_csv(inv_file)
            st.session_state[INV_RAW] = inv_df
            st.success("Inventory loaded")

    with col2:
        sales_file = st.file_uploader("Upload Sales CSV", type=["csv"], key="sales_upload")
        if sales_file:
            sales_df = pd.read_csv(sales_file)
            st.session_state[SALES_RAW] = sales_df
            st.success("Sales loaded")

    inv_df = st.session_state.get(INV_RAW)
    sales_df = st.session_state.get(SALES_RAW)

    stats = st.columns(2)
    with stats[0]:
        render_metric_card("Inventory Rows", len(inv_df) if isinstance(inv_df, pd.DataFrame) else 0)
    with stats[1]:
        render_metric_card("Sales Rows", len(sales_df) if isinstance(sales_df, pd.DataFrame) else 0)

    if st.button("Prepare Buyer Dataset"):
        prepared = _prepare_buyer_dataset(inv_df, sales_df)
        st.session_state[BUYER_READY] = prepared
        st.success("Buyer dataset prepared for Doobie")

    if isinstance(inv_df, pd.DataFrame):
        st.subheader("Inventory Preview")
        st.dataframe(inv_df.head(50), use_container_width=True)

    if isinstance(sales_df, pd.DataFrame):
        st.subheader("Sales Preview")
        st.dataframe(sales_df.head(50), use_container_width=True)
