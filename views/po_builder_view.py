import streamlit as st
import pandas as pd

from services.purchasing_context import purchasing_frame
from ui.components import render_section_header, render_metric_card


def render_po_builder_view():
    render_section_header("PO Builder", "Build purchase orders from Buyer Dash's active inventory and demand data")

    df = purchasing_frame(st.session_state)

    if not isinstance(df, pd.DataFrame) or df.empty:
        st.warning("No purchasing data is available for the active facility yet. Import inventory and sales in Data Hub, or select a populated tenant.")
        return

    render_metric_card("Products Available", len(df), "Current products available for ordering decisions")

    st.subheader("Select Products for PO")
    preferred = [
        "product_name",
        "sku",
        "subcategory",
        "primary_vendor",
        "vendor_lead_time_days",
        "vendor_moq",
        "vendor_case_pack",
        "onhandunits",
        "unitssold",
        "avgunitsperday",
        "daysonhand",
        "open_po_units",
        "production_demand_units",
        "unit_cost",
        "reorderqty",
        "reorderpriority",
    ]
    visible = [column for column in preferred if column in df.columns]
    selectable = df[visible].copy() if visible else df.copy()
    selectable["Order Qty"] = pd.to_numeric(selectable.get("reorderqty", 0), errors="coerce").fillna(0).clip(lower=0).astype(int)

    edited = st.data_editor(selectable.head(100), use_container_width=True, hide_index=True)

    if st.button("Generate PO Preview", type="primary"):
        selected = edited[pd.to_numeric(edited["Order Qty"], errors="coerce").fillna(0) > 0]

        if selected.empty:
            st.warning("No products selected")
        else:
            st.success("PO Preview Generated")
            st.dataframe(selected, use_container_width=True, hide_index=True)
