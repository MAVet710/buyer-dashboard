import streamlit as st
from pos_automap import read_tabular_auto, automap_inventory, automap_sales, normalize_inventory_for_session, normalize_sales_for_session, detect_pos_source

from core.session_keys import INV_RAW, SALES_RAW


def render_inventory_automap():
    st.title("Smart Upload (Auto Map)")

    inv_file = st.file_uploader("Upload Inventory", type=["csv","xlsx","xls"], key="auto_inv")
    sales_file = st.file_uploader("Upload Sales", type=["csv","xlsx","xls"], key="auto_sales")

    if inv_file:
        inv_df = read_tabular_auto(inv_file, "inventory")
        src = detect_pos_source(inv_df)
        st.success(f"Detected Inventory Source: {src}")

        mapping, ok = automap_inventory(inv_df)
        st.write("Detected Columns:", mapping)

        if ok:
            norm = normalize_inventory_for_session(inv_df, mapping)
            st.session_state[INV_RAW] = norm
            st.success("Inventory mapped and loaded")
            st.dataframe(norm.head(50))
        else:
            st.error("Could not fully map inventory columns")

    if sales_file:
        sales_df = read_tabular_auto(sales_file, "sales")
        src = detect_pos_source(sales_df)
        st.success(f"Detected Sales Source: {src}")

        mapping, ok = automap_sales(sales_df)
        st.write("Detected Columns:", mapping)

        if ok:
            norm = normalize_sales_for_session(sales_df, mapping)
            st.session_state[SALES_RAW] = norm
            st.success("Sales mapped and loaded")
            st.dataframe(norm.head(50))
        else:
            st.error("Could not fully map sales columns")
