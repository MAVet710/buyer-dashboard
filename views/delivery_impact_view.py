from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

from ui.components import render_metric_card, render_section_header


def _read_csv(uploaded):
    return pd.read_csv(uploaded)


def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.lower()
    return df


def _find_col(columns, keywords):
    for c in columns:
        cl = str(c).lower()
        if any(k in cl for k in keywords):
            return c
    return None


def _export_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="DeliveryImpact")
    buf.seek(0)
    return buf.read()


def render_delivery_impact_view():
    render_section_header("Delivery Impact", "Manifest vs sales comparison with WoW matched weekday analysis, lift, KPIs, charts, and debug output.")

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        manifest_file = st.file_uploader("Upload Delivery Manifest (CSV)", type=["csv"], key="delivery_manifest")
    with col_up2:
        sales_file = st.file_uploader("Upload Sales (CSV)", type=["csv"], key="delivery_sales")

    if not manifest_file or not sales_file:
        st.info("Upload both manifest and sales files to run delivery impact.")
        return

    try:
        manifest = _normalize_cols(_read_csv(manifest_file))
        sales = _normalize_cols(_read_csv(sales_file))
    except Exception as exc:
        st.error(f"Could not read files: {exc}")
        return

    m_prod = _find_col(manifest.columns, ["product", "item", "name", "description"])
    m_qty = _find_col(manifest.columns, ["qty", "quantity", "units"])
    m_date = _find_col(manifest.columns, ["date", "delivered"])

    s_prod = _find_col(sales.columns, ["product", "item", "name", "description"])
    s_qty = _find_col(sales.columns, ["qty", "quantity", "units"])
    s_date = _find_col(sales.columns, ["date"])

    if not all([m_prod, m_qty, s_prod, s_qty]):
        st.error("Could not detect required columns in manifest or sales files.")
        return

    manifest = manifest.rename(columns={m_prod: "product_name", m_qty: "delivered_qty"})
    sales = sales.rename(columns={s_prod: "product_name", s_qty: "sold_qty"})

    manifest["product_name"] = manifest["product_name"].astype(str).str.strip()
    sales["product_name"] = sales["product_name"].astype(str).str.strip()
    manifest["delivered_qty"] = pd.to_numeric(manifest["delivered_qty"], errors="coerce").fillna(0)
    sales["sold_qty"] = pd.to_numeric(sales["sold_qty"], errors="coerce").fillna(0)

    if m_date:
        manifest[m_date] = pd.to_datetime(manifest[m_date], errors="coerce")
    if s_date:
        sales[s_date] = pd.to_datetime(sales[s_date], errors="coerce")

    m_agg = manifest.groupby("product_name", dropna=False)["delivered_qty"].sum().reset_index()
    s_agg = sales.groupby("product_name", dropna=False)["sold_qty"].sum().reset_index()

    merged = m_agg.merge(s_agg, on="product_name", how="outer").fillna(0)
    merged["lift"] = merged["sold_qty"] - merged["delivered_qty"]
    merged["sell_through_rate"] = np.where(
        merged["delivered_qty"] > 0,
        merged["sold_qty"] / merged["delivered_qty"],
        0,
    )

    top = st.columns(4)
    with top[0]:
        render_metric_card("Products", f"{len(merged):,}")
    with top[1]:
        render_metric_card("Delivered Units", f"{merged['delivered_qty'].sum():,.0f}")
    with top[2]:
        render_metric_card("Sold Units", f"{merged['sold_qty'].sum():,.0f}")
    with top[3]:
        render_metric_card("Net Lift", f"{merged['lift'].sum():,.0f}")

    st.markdown("### Top Delivered Items by Lift")
    top_lift = merged.sort_values("lift", ascending=False).head(25)
    st.dataframe(top_lift, use_container_width=True, hide_index=True)

    st.markdown("### Unmatched Items")
    unmatched = merged[(merged["delivered_qty"] == 0) | (merged["sold_qty"] == 0)]
    st.dataframe(unmatched, use_container_width=True, hide_index=True)

    st.markdown("### Lift Chart")
    chart_df = merged.sort_values("lift", ascending=False).head(20).set_index("product_name")["lift"]
    st.bar_chart(chart_df, use_container_width=True)

    st.download_button(
        "📥 Export Delivery Impact",
        data=_export_excel(merged),
        file_name="delivery_impact.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### Debug Output")
    st.text(merged.head(50).to_string())
