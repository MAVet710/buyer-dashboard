import streamlit as st
import pandas as pd

from ui.components import render_section_header, render_metric_card


def render_po_builder_view():
    render_section_header("PO Builder", "Commercial-ready purchase order generator (initial migration)")

    st.info("This is the modular PO Builder shell. Next step will connect Doobie recommendations directly into PO suggestions.")

    df = st.session_state.get("detail_product_cached_df")

    if not isinstance(df, pd.DataFrame) or df.empty:
        st.warning("No buyer dataset available. Go to Inventory Prep first.")
        return

    render_metric_card("Products Available", len(df), "Rows available for ordering decisions")

    st.subheader("Select Products for PO")
    selectable = df.copy()

    selectable["Order Qty"] = 0

    edited = st.data_editor(selectable.head(50), use_container_width=True)

    if st.button("Generate PO Preview"):
        selected = edited[edited["Order Qty"] > 0]

        if selected.empty:
            st.warning("No products selected")
        else:
            st.success("PO Preview Generated")
            st.dataframe(selected, use_container_width=True)
