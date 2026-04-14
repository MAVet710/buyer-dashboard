import re
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

from core.session_keys import INV_RAW, SALES_RAW
from ui.components import render_metric_card, render_section_header


UNKNOWN_DOH = 999


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _detect(columns, aliases):
    cmap = {_norm(c): c for c in columns}
    for alias in aliases:
        if alias in cmap:
            return cmap[alias]
    return None


def _currency_to_float(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"^\$", "", regex=True)
        .str.replace(",", "", regex=False)
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
    )


def _normalize_category(raw):
    if pd.isna(raw):
        return "unknown"
    s = str(raw).strip().lower()
    if any(k in s for k in ["flower", "bud"]):
        return "flower"
    if any(k in s for k in ["pre roll", "preroll", "joint"]):
        return "pre rolls"
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        return "vapes"
    if any(k in s for k in ["edible", "gummy", "chocolate", "chew"]):
        return "edibles"
    if any(k in s for k in ["beverage", "drink", "shot"]):
        return "beverages"
    if any(k in s for k in ["concentrate", "wax", "shatter", "resin", "rosin", "dab"]):
        return "concentrates"
    if any(k in s for k in ["tincture", "drops"]):
        return "tinctures"
    if any(k in s for k in ["topical", "cream", "salve", "balm"]):
        return "topicals"
    return s or "unknown"


def _export_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="SlowMovers")
    buf.seek(0)
    return buf.read()


def _build_slow_movers(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, velocity_days: int) -> pd.DataFrame:
    inv = inv_raw_df.copy()
    sales = sales_raw_df.copy()
    inv.columns = inv.columns.astype(str).str.strip().str.lower()
    sales.columns = sales.columns.astype(str).str.strip().str.lower()

    inv_name = _detect(inv.columns, ["product", "productname", "item", "itemname", "name", "productname"])
    inv_cat = _detect(inv.columns, ["category", "subcategory", "productcategory", "department", "mastercategory"])
    inv_qty = _detect(inv.columns, ["available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand", "instock"])
    inv_brand = _detect(inv.columns, ["brand", "brandname", "vendor", "vendorname", "manufacturer", "producer"])
    inv_cost = _detect(inv.columns, ["cost", "unitcost", "cogs", "wholesaleprice", "wholesale"])
    inv_retail = _detect(inv.columns, ["retail", "retailprice", "medprice", "msrp"])
    if not (inv_name and inv_cat and inv_qty):
        raise ValueError("Could not detect inventory product/category/on-hand columns.")

    inv = inv.rename(columns={inv_name: "product_name", inv_cat: "category", inv_qty: "onhandunits"})
    if inv_brand:
        inv = inv.rename(columns={inv_brand: "brand"})
    if inv_cost:
        inv = inv.rename(columns={inv_cost: "unit_cost"})
    if inv_retail:
        inv = inv.rename(columns={inv_retail: "retail_price"})
    inv["product_name"] = inv["product_name"].astype(str).str.strip()
    inv["category"] = inv["category"].apply(_normalize_category)
    inv["onhandunits"] = pd.to_numeric(inv["onhandunits"], errors="coerce").fillna(0)
    if "unit_cost" in inv.columns:
        inv["unit_cost"] = _currency_to_float(inv["unit_cost"]).fillna(0)
    if "retail_price" in inv.columns:
        inv["retail_price"] = _currency_to_float(inv["retail_price"]).fillna(0)

    invg = inv.groupby(["product_name", "category"], dropna=False).agg(
        onhandunits=("onhandunits", "sum"),
        brand=("brand", "first") if "brand" in inv.columns else ("product_name", "first"),
        unit_cost=("unit_cost", "median") if "unit_cost" in inv.columns else ("onhandunits", "size"),
        retail_price=("retail_price", "median") if "retail_price" in inv.columns else ("onhandunits", "size"),
    ).reset_index()
    if "unit_cost" not in invg.columns:
        invg["unit_cost"] = 0.0
    if "retail_price" not in invg.columns:
        invg["retail_price"] = 0.0

    sales_name = _detect(sales.columns, ["product", "productname", "name", "item", "itemname", "producttitle"])
    sales_qty = _detect(sales.columns, ["quantitysold", "qtysold", "unitssold", "quantity", "qty", "items sold", "itemssold"])
    sales_cat = _detect(sales.columns, ["category", "mastercategory", "productcategory", "department", "subcategory"])
    sales_date = next((c for c in sales.columns if "date" in c), None)
    if not (sales_name and sales_qty and sales_cat):
        raise ValueError("Could not detect sales product/quantity/category columns.")
    sales = sales.rename(columns={sales_name: "product_name", sales_qty: "unitssold", sales_cat: "category"})
    sales["product_name"] = sales["product_name"].astype(str).str.strip()
    sales["category"] = sales["category"].apply(_normalize_category)
    sales["unitssold"] = pd.to_numeric(sales["unitssold"], errors="coerce").fillna(0)
    if sales_date:
        sales[sales_date] = pd.to_datetime(sales[sales_date], errors="coerce")
        cutoff = sales[sales_date].max() - pd.Timedelta(days=velocity_days)
        sales = sales[sales[sales_date] >= cutoff].copy()
    sal = sales.groupby(["product_name", "category"], dropna=False)["unitssold"].sum().reset_index()
    sal["daily_run_rate"] = sal["unitssold"] / max(velocity_days, 1)

    df = invg.merge(sal, on=["product_name", "category"], how="left")
    df["unitssold"] = df["unitssold"].fillna(0)
    df["daily_run_rate"] = df["daily_run_rate"].fillna(0)
    df["days_on_hand"] = np.where(df["daily_run_rate"] > 0, df["onhandunits"] / df["daily_run_rate"], UNKNOWN_DOH)
    df["inventory_cost"] = df["onhandunits"] * pd.to_numeric(df["unit_cost"], errors="coerce").fillna(0)
    df["inventory_retail"] = df["onhandunits"] * pd.to_numeric(df["retail_price"], errors="coerce").fillna(0)

    overall_daily = df["daily_run_rate"].mean() if len(df) else 0
    df["velocity_band"] = np.where(
        df["daily_run_rate"] <= overall_daily * 0.5,
        "Slow",
        np.where(df["daily_run_rate"] <= overall_daily * 1.2, "Normal", "Fast")
    )

    def decision(row):
        doh = row["days_on_hand"]
        sold = row["unitssold"]
        if sold <= 0 and row["onhandunits"] > 0:
            return "Dead item"
        if doh >= 180:
            return "Aggressive markdown"
        if doh >= 120:
            return "Markdown candidate"
        if doh >= 90:
            return "Watch closely"
        return "Healthy"

    def discount_tier(row):
        doh = row["days_on_hand"]
        if row["unitssold"] <= 0 and row["onhandunits"] > 0:
            return "35%+"
        if doh >= 180:
            return "30%"
        if doh >= 120:
            return "25%"
        if doh >= 90:
            return "15%"
        return "No discount"

    df["decision"] = df.apply(decision, axis=1)
    df["discount_tier"] = df.apply(discount_tier, axis=1)
    return df.sort_values(["days_on_hand", "inventory_cost"], ascending=[False, False])


def render_slow_movers_view():
    render_section_header("Slow Movers", "Decision-first slow mover workflow with filters, DOH scoring, discount tiers, and export.")

    inv_raw_df = st.session_state.get(INV_RAW)
    sales_raw_df = st.session_state.get(SALES_RAW)
    if not isinstance(inv_raw_df, pd.DataFrame) or not isinstance(sales_raw_df, pd.DataFrame):
        st.warning("Inventory and Product Sales uploads are required. Use Inventory Prep first.")
        return

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        velocity_days = int(st.selectbox("Velocity Window", [14, 28, 56, 84], index=2, key="slow_velocity_days"))
    with f2:
        min_doh = float(st.number_input("Min DOH Threshold", min_value=0.0, value=90.0, step=5.0, key="slow_min_doh"))
    with f3:
        top_n = int(st.selectbox("Top N", [25, 50, 100, 250, 500], index=2, key="slow_top_n"))
    with f4:
        search = st.text_input("Search Product", key="slow_search").strip().lower()

    try:
        slow_df = _build_slow_movers(inv_raw_df, sales_raw_df, velocity_days=velocity_days)
    except Exception as exc:
        st.error(f"Could not build slow movers view: {exc}")
        return

    categories = sorted(slow_df["category"].dropna().astype(str).unique().tolist())
    brands = sorted(slow_df["brand"].dropna().astype(str).unique().tolist()) if "brand" in slow_df.columns else []
    c1, c2, c3 = st.columns(3)
    with c1:
        selected_categories = st.multiselect("Categories", categories, default=categories, key="slow_categories")
    with c2:
        selected_brands = st.multiselect("Brands", brands, default=brands[: min(len(brands), 30)] if brands else [], key="slow_brands")
        if not selected_brands and brands:
            selected_brands = brands
    with c3:
        decisions = sorted(slow_df["decision"].dropna().astype(str).unique().tolist())
        selected_decisions = st.multiselect("Decision", decisions, default=decisions, key="slow_decisions")

    view = slow_df.copy()
    view = view[view["days_on_hand"] >= min_doh]
    if selected_categories:
        view = view[view["category"].isin(selected_categories)]
    if brands and selected_brands:
        view = view[view["brand"].isin(selected_brands)]
    if selected_decisions:
        view = view[view["decision"].isin(selected_decisions)]
    if search:
        view = view[view["product_name"].astype(str).str.lower().str.contains(search, na=False)]
    view = view.head(top_n)

    top = st.columns(4)
    with top[0]:
        render_metric_card("Slow SKUs", f"{len(view):,}", "Filtered result count")
    with top[1]:
        render_metric_card("Inventory Cost", f"${view['inventory_cost'].sum():,.0f}", "Cost tied in filtered slow movers")
    with top[2]:
        dead_items = int((view["decision"] == "Dead item").sum())
        render_metric_card("Dead Items", f"{dead_items:,}", "Zero-sales products with inventory")
    with top[3]:
        markdown_items = int(view["decision"].isin(["Markdown candidate", "Aggressive markdown"]).sum())
        render_metric_card("Markdown Candidates", f"{markdown_items:,}", "Products needing discount action")

    st.markdown("### Discount Tier Summary")
    tier_summary = view.groupby("discount_tier", dropna=False).agg(
        skus=("product_name", "count"),
        inventory_cost=("inventory_cost", "sum"),
        inventory_retail=("inventory_retail", "sum"),
    ).reset_index().sort_values("inventory_cost", ascending=False)
    st.dataframe(tier_summary, use_container_width=True, hide_index=True)

    st.markdown("### Decision-First Table")
    cols = [c for c in ["decision", "discount_tier", "product_name", "brand", "category", "onhandunits", "unitssold", "daily_run_rate", "days_on_hand", "inventory_cost", "inventory_retail", "velocity_band"] if c in view.columns]
    st.dataframe(view[cols], use_container_width=True, hide_index=True)
    st.download_button(
        "📥 Export Slow Movers (Excel)",
        data=_export_excel(view[cols]),
        file_name="slow_movers.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="slow_export",
    )
