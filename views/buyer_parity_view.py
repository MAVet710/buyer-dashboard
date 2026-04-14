import re
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

from core.session_keys import BUYER_READY, INV_RAW, SALES_RAW
from ui.components import render_metric_card, render_section_header

UNKNOWN_DAYS_OF_SUPPLY = 999
INVENTORY_REORDER_DOH_THRESHOLD = 21
INVENTORY_OVERSTOCK_DOH_THRESHOLD = 90
INVENTORY_EXPIRING_SOON_DAYS = 60
PRODUCT_TABLE_DISPLAY_LIMIT = 2000


def _normalize_col(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _detect_column(columns, aliases):
    norm_map = {_normalize_col(c): c for c in columns}
    for alias in aliases:
        if alias in norm_map:
            return norm_map[alias]
    return None


def _parse_currency_to_float(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"^\$", "", regex=True)
        .str.replace(",", "", regex=False)
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
    )


def _build_forecast_export_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Forecast")
    buf.seek(0)
    return buf.read()


def _safe_num(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _build_sku_inventory_view(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, vel_window: int = 56) -> pd.DataFrame:
    inv = inv_raw_df.copy()
    sales = sales_raw_df.copy()

    inv.columns = inv.columns.astype(str).str.strip().str.lower()
    sales.columns = sales.columns.astype(str).str.strip().str.lower()

    INV_NAME_ALIASES = ["product", "productname", "item", "itemname", "name", "product name"]
    INV_CAT_ALIASES = ["category", "subcategory", "productcategory", "department", "product category"]
    INV_QTY_ALIASES = ["available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand"]
    INV_SKU_ALIASES = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
    INV_COST_ALIASES = ["cost", "unitcost", "unit cost", "cogs", "wholesaleprice", "wholesale price"]
    INV_RETAIL_PRICE_ALIASES = ["medprice", "med price", "retail", "retailprice", "retail price", "msrp"]
    INV_BRAND_ALIASES = ["brand", "brandname", "brand name", "vendor", "vendorname", "vendor name", "manufacturer"]
    INV_EXPIRY_ALIASES = ["expirationdate", "expiration date", "expiry", "expirydate", "expiry date", "best by"]

    SALES_NAME_ALIASES = ["product", "productname", "product title", "producttitle", "productid", "name", "item", "itemname", "sku", "description", "product name"]
    SALES_QTY_ALIASES = ["quantitysold", "quantity sold", "qtysold", "qty sold", "items sold", "unitssold", "units sold", "units", "quantity", "qty"]

    inv_name_col = _detect_column(inv.columns, [_normalize_col(a) for a in INV_NAME_ALIASES])
    inv_qty_col = _detect_column(inv.columns, [_normalize_col(a) for a in INV_QTY_ALIASES])
    if not (inv_name_col and inv_qty_col):
        return pd.DataFrame()

    rename_map = {inv_name_col: "itemname", inv_qty_col: "onhandunits"}
    for aliases, target in [
        (INV_CAT_ALIASES, "category"),
        (INV_SKU_ALIASES, "sku"),
        (INV_COST_ALIASES, "unit_cost"),
        (INV_RETAIL_PRICE_ALIASES, "retail_price"),
        (INV_BRAND_ALIASES, "brand_vendor"),
        (INV_EXPIRY_ALIASES, "expiration_date"),
    ]:
        found = _detect_column(inv.columns, [_normalize_col(a) for a in aliases])
        if found:
            rename_map[found] = target

    inv = inv.rename(columns=rename_map)
    inv["itemname"] = inv["itemname"].astype(str).str.strip()
    inv["onhandunits"] = pd.to_numeric(inv["onhandunits"], errors="coerce").fillna(0)
    if "unit_cost" in inv.columns:
        inv["unit_cost"] = _parse_currency_to_float(inv["unit_cost"])
    if "retail_price" in inv.columns:
        inv["retail_price"] = _parse_currency_to_float(inv["retail_price"])
    if "expiration_date" in inv.columns:
        inv["expiration_date"] = pd.to_datetime(inv["expiration_date"], errors="coerce")

    agg_map = {"onhandunits": "sum"}
    for c in ["unit_cost", "retail_price", "brand_vendor", "category", "sku"]:
        if c in inv.columns:
            agg_map[c] = "first"
    if "expiration_date" in inv.columns:
        agg_map["expiration_date"] = "min"
    sku_df = inv.groupby("itemname", dropna=False).agg(agg_map).reset_index()

    sales_name_col = _detect_column(sales.columns, [_normalize_col(a) for a in SALES_NAME_ALIASES])
    sales_qty_col = _detect_column(sales.columns, [_normalize_col(a) for a in SALES_QTY_ALIASES])
    if not (sales_name_col and sales_qty_col):
        sku_df["total_sold"] = 0
        sku_df["daily_run_rate"] = 0
        sku_df["avg_weekly_sales"] = 0
    else:
        sales[sales_qty_col] = pd.to_numeric(sales[sales_qty_col], errors="coerce").fillna(0)
        date_cols = [c for c in sales.columns if "date" in c]
        if date_cols:
            date_col = date_cols[0]
            sales[date_col] = pd.to_datetime(sales[date_col], errors="coerce")
            cutoff = sales[date_col].max() - pd.Timedelta(days=vel_window)
            sales = sales[sales[date_col] >= cutoff].copy()
        vel = (
            sales.groupby(sales_name_col)[sales_qty_col]
            .sum()
            .reset_index()
            .rename(columns={sales_name_col: "itemname", sales_qty_col: "total_sold"})
        )
        vel["daily_run_rate"] = vel["total_sold"] / max(vel_window, 1)
        vel["avg_weekly_sales"] = vel["daily_run_rate"] * 7
        sku_df = sku_df.merge(vel, on="itemname", how="left")
        for c in ["total_sold", "daily_run_rate", "avg_weekly_sales"]:
            sku_df[c] = sku_df[c].fillna(0)

    sku_df["days_of_supply"] = np.where(
        sku_df["daily_run_rate"] > 0,
        sku_df["onhandunits"] / sku_df["daily_run_rate"],
        UNKNOWN_DAYS_OF_SUPPLY,
    )
    sku_df["weeks_of_supply"] = (sku_df["days_of_supply"] / 7).round(1)
    if "unit_cost" in sku_df.columns:
        sku_df["dollars_on_hand"] = sku_df["onhandunits"] * sku_df["unit_cost"]
    if "retail_price" in sku_df.columns:
        sku_df["retail_dollars_on_hand"] = sku_df["onhandunits"] * sku_df["retail_price"]
    if "expiration_date" in sku_df.columns:
        today = pd.Timestamp.today().normalize()
        sku_df["days_to_expire"] = (sku_df["expiration_date"] - today).dt.days

    def status(row):
        if row["onhandunits"] <= 0:
            return "⬛ No Stock"
        if "days_to_expire" in row.index and pd.notna(row.get("days_to_expire")) and row.get("days_to_expire") < INVENTORY_EXPIRING_SOON_DAYS:
            return "⚠️ Expiring"
        if 0 < row["days_of_supply"] <= INVENTORY_REORDER_DOH_THRESHOLD:
            return "🔴 Reorder"
        if row["days_of_supply"] >= INVENTORY_OVERSTOCK_DOH_THRESHOLD:
            return "🟠 Overstock"
        return "✅ Healthy"

    sku_df["status"] = sku_df.apply(status, axis=1)
    return sku_df


def render_buyer_parity_view():
    render_section_header(
        "Buyer Dashboard Parity",
        "Brings the original buyer-facing outputs into the modular app first: Category DOS, Forecast Table, Product Rows, and SKU Buyer View.",
    )

    detail_df = st.session_state.get("detail_cached_df")
    detail_product_df = st.session_state.get(BUYER_READY) or st.session_state.get("detail_product_cached_df")
    inv_raw_df = st.session_state.get(INV_RAW)
    sales_raw_df = st.session_state.get(SALES_RAW)

    if not isinstance(detail_df, pd.DataFrame) or detail_df.empty:
        st.warning(
            "No prepared buyer forecast dataset found yet. Load the original inventory workflow first, or use Inventory Prep to begin staging the modular replacement."
        )
        return

    top = st.columns(4)
    with top[0]:
        render_metric_card("Forecast Rows", f"{len(detail_df):,}", "Current category/size forecast rows")
    with top[1]:
        reorder_now = int((detail_df.get("reorderpriority", pd.Series(dtype=str)) == "1 – Reorder ASAP").sum())
        render_metric_card("Reorder ASAP", f"{reorder_now:,}", "Immediate priority lines")
    with top[2]:
        units_sold = _safe_num(pd.to_numeric(detail_df.get("unitssold", 0), errors="coerce").sum())
        render_metric_card("Units Sold", f"{units_sold:,.0f}", "Granular size-level units sold")
    with top[3]:
        onhand = _safe_num(pd.to_numeric(detail_df.get("onhandunits", 0), errors="coerce").sum())
        render_metric_card("On Hand", f"{onhand:,.0f}", "Current units across filtered forecast rows")

    tabs = st.tabs([
        "Category DOS",
        "Forecast Table",
        "Product Rows",
        "SKU Buyer View",
    ])

    with tabs[0]:
        st.markdown("### Category DOS (at a glance)")
        cat_quick = (
            detail_df.groupby("subcategory", dropna=False)
            .agg(
                onhandunits=("onhandunits", "sum"),
                avgunitsperday=("avgunitsperday", "sum"),
                reorder_lines=("reorderpriority", lambda x: int((x == "1 – Reorder ASAP").sum())),
            )
            .reset_index()
        )
        cat_quick["category_dos"] = np.where(
            pd.to_numeric(cat_quick["avgunitsperday"], errors="coerce").fillna(0) > 0,
            pd.to_numeric(cat_quick["onhandunits"], errors="coerce").fillna(0)
            / pd.to_numeric(cat_quick["avgunitsperday"], errors="coerce").replace(0, np.nan),
            0,
        )
        cat_quick["category_dos"] = cat_quick["category_dos"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)

        if isinstance(detail_product_df, pd.DataFrame) and not detail_product_df.empty and "product_name" in detail_product_df.columns:
            dp = detail_product_df[["subcategory", "product_name", "unitssold"]].copy()
            dp["unitssold"] = pd.to_numeric(dp["unitssold"], errors="coerce").fillna(0)
            top_products = (
                dp.sort_values("unitssold", ascending=False)
                .groupby("subcategory", dropna=False, sort=False)["product_name"]
                .apply(lambda x: ", ".join(x.astype(str).head(5).tolist()))
                .reset_index()
                .rename(columns={"product_name": "top_products"})
            )
            product_count = (
                dp.groupby("subcategory", dropna=False)["product_name"]
                .nunique()
                .reset_index()
                .rename(columns={"product_name": "product_count"})
            )
            cat_quick = cat_quick.merge(top_products, on="subcategory", how="left")
            cat_quick = cat_quick.merge(product_count, on="subcategory", how="left")
            cat_quick["product_count"] = cat_quick["product_count"].fillna(0).astype(int)
            cat_quick["top_products"] = cat_quick["top_products"].fillna("")

        cols = ["subcategory", "category_dos", "reorder_lines"]
        if "product_count" in cat_quick.columns:
            cols += ["product_count", "top_products"]
        st.dataframe(
            cat_quick[cols].sort_values(["reorder_lines", "category_dos"], ascending=[False, True]),
            use_container_width=True,
            hide_index=True,
        )

    with tabs[1]:
        st.markdown("### Forecast Table")
        show_only_reorder = st.toggle("Only show Reorder ASAP", value=False, key="buyer_parity_reorder_only")
        forecast_view = detail_df.copy()
        if show_only_reorder and "reorderpriority" in forecast_view.columns:
            forecast_view = forecast_view[forecast_view["reorderpriority"] == "1 – Reorder ASAP"]

        display_cols = [
            "top_products",
            "mastercategory",
            "subcategory",
            "strain_type",
            "packagesize",
            "onhandunits",
            "unitssold",
            "avgunitsperday",
            "daysonhand",
            "reorderqty",
            "reorderpriority",
            "product_count",
        ]
        display_cols = [c for c in display_cols if c in forecast_view.columns]
        st.dataframe(forecast_view[display_cols], use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Export Forecast Table (Excel)",
            data=_build_forecast_export_bytes(forecast_view[display_cols]),
            file_name="forecast_table.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="buyer_parity_export_forecast",
        )

    with tabs[2]:
        st.markdown("### Product-Level Rows")
        if not isinstance(detail_product_df, pd.DataFrame) or detail_product_df.empty:
            st.info("No prepared product-level dataset found yet.")
        else:
            dpv = detail_product_df.copy()
            if len(dpv) > PRODUCT_TABLE_DISPLAY_LIMIT:
                st.caption(f"⚠️ Showing top {PRODUCT_TABLE_DISPLAY_LIMIT} rows by units sold.")
                if "unitssold" in dpv.columns:
                    dpv = dpv.sort_values("unitssold", ascending=False).head(PRODUCT_TABLE_DISPLAY_LIMIT)
                else:
                    dpv = dpv.head(PRODUCT_TABLE_DISPLAY_LIMIT)
            prod_cols = [
                "product_name", "subcategory", "strain_type", "packagesize",
                "onhandunits", "unitssold", "avgunitsperday", "daysonhand",
            ]
            prod_cols = [c for c in prod_cols if c in dpv.columns]
            st.dataframe(dpv[prod_cols], use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Download Product-Level Table (Excel)",
                data=_build_forecast_export_bytes(dpv[prod_cols]),
                file_name="product_level_forecast.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="buyer_parity_export_product",
            )

    with tabs[3]:
        st.markdown("### SKU Inventory Buyer View")
        if not isinstance(inv_raw_df, pd.DataFrame) or not isinstance(sales_raw_df, pd.DataFrame):
            st.info("Inventory and sales raw uploads are required for the SKU Buyer View.")
        else:
            vel_window = st.selectbox("Velocity window", [28, 56, 84], index=1, key="buyer_parity_vel_window")
            sku_df = _build_sku_inventory_view(inv_raw_df, sales_raw_df, vel_window=vel_window)
            if sku_df.empty:
                st.warning("Could not build the SKU Buyer View from the currently loaded data.")
            else:
                tab_all, tab_reorder, tab_overstock, tab_exp = st.tabs([
                    "📦 All Inventory", "🔴 Reorder", "🟠 Overstock", "⚠️ Expiring"
                ])

                def render_table(df: pd.DataFrame):
                    if df.empty:
                        st.success("✅ No SKUs match the current filters.")
                        return
                    st.dataframe(df, use_container_width=True, hide_index=True)

                cols_order = [
                    c for c in [
                        "sku", "itemname", "brand_vendor", "category", "onhandunits", "avg_weekly_sales",
                        "days_of_supply", "weeks_of_supply", "dollars_on_hand", "retail_dollars_on_hand",
                        "expiration_date", "days_to_expire", "status"
                    ] if c in sku_df.columns
                ]

                with tab_all:
                    render_table(sku_df[cols_order])
                with tab_reorder:
                    render_table(sku_df[sku_df["days_of_supply"] <= INVENTORY_REORDER_DOH_THRESHOLD][cols_order])
                with tab_overstock:
                    render_table(sku_df[sku_df["days_of_supply"] >= INVENTORY_OVERSTOCK_DOH_THRESHOLD][cols_order])
                with tab_exp:
                    if "days_to_expire" in sku_df.columns:
                        render_table(sku_df[sku_df["days_to_expire"].notna() & (sku_df["days_to_expire"] < INVENTORY_EXPIRING_SOON_DAYS)][cols_order])
                    else:
                        st.info("No expiration date column detected in inventory file.")
