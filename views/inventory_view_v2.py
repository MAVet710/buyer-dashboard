import pandas as pd
import streamlit as st

from ui.components import render_section_header, render_metric_card
from core.session_keys import BUYER_READY
from services.inventory_state import (
    clear_active_inventory,
    clear_active_sales,
    get_active_inventory_df,
    get_active_sales_df,
    set_active_inventory_df,
    set_active_sales_df,
)


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
            set_active_inventory_df(inv_df, source_name=getattr(inv_file, "name", "file"), source_type="upload")
            st.success(f"Inventory loaded: {getattr(inv_file, 'name', 'file')}")
    with col2:
        sales_file = st.file_uploader("Upload Sales File", type=["csv", "xlsx", "xls"], key="sales_upload_v2")
        if sales_file:
            sales_df = _read_tabular(sales_file)
            set_active_sales_df(sales_df, source_name=getattr(sales_file, "name", "file"), source_type="upload")
            st.success(f"Sales loaded: {getattr(sales_file, 'name', 'file')}")

    inv_df, inv_meta = get_active_inventory_df()
    sales_df, sales_meta = get_active_sales_df()


    with st.expander("Active Inventory Source", expanded=True):
        if isinstance(inv_df, pd.DataFrame) and not inv_df.empty:
            st.write(f"Status: {inv_meta.get('status', 'Loaded')}")
            st.write(f"File: {inv_meta.get('source_name') or 'Unknown'}")
            st.write(f"Rows: {inv_meta.get('rows', 0)}")
            st.write(f"Columns: {len(inv_meta.get('columns', []))}")
            st.write(f"Uploaded at (UTC): {inv_meta.get('uploaded_at') or 'Unknown'}")
            st.write(f"Source key: {inv_meta.get('source_key') or 'Unknown'}")
        else:
            st.warning("Upload inventory in Buyer Dashboard Inventory Upload to unlock this section.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear Active Inventory", key="clear_active_inventory_v2"):
            clear_active_inventory()
            st.success("Active inventory cleared.")
    with c2:
        if st.button("Clear Active Sales", key="clear_active_sales_v2"):
            clear_active_sales()
            st.success("Active sales cleared.")

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

    if st.session_state.get("is_admin", False):
        with st.expander("Inventory Session Debug", expanded=False):
            buyer_ready = st.session_state.get(BUYER_READY)
            st.write(f"active_inventory_df present: {isinstance(st.session_state.get('active_inventory_df'), pd.DataFrame)}")
            st.write(f"inv_raw_df present: {isinstance(st.session_state.get('inv_raw_df'), pd.DataFrame)}")
            st.write(f"detail_product_cached_df present: {isinstance(buyer_ready, pd.DataFrame)}")
            st.write(f"active_sales_df present: {isinstance(st.session_state.get('active_sales_df'), pd.DataFrame)}")
            st.write(f"sales_raw_df present: {isinstance(st.session_state.get('sales_raw_df'), pd.DataFrame)}")
            st.write(f"active inventory rows: {len(inv_df) if isinstance(inv_df, pd.DataFrame) else 0}")
            st.write(f"active sales rows: {len(sales_df) if isinstance(sales_df, pd.DataFrame) else 0}")
