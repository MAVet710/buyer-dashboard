import re
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

from core.session_keys import INV_RAW, SALES_RAW, BUYER_READY
from doobie_panels import run_buyer_doobie
from ui.components import render_metric_card, render_section_header

UNKNOWN_DAYS_OF_SUPPLY = 999
PRODUCT_TABLE_DISPLAY_LIMIT = 2000
INVENTORY_REORDER_DOH_THRESHOLD = 21
INVENTORY_OVERSTOCK_DOH_THRESHOLD = 90
INVENTORY_EXPIRING_SOON_DAYS = 60
REB_CATEGORIES = [
    "flower", "pre rolls", "vapes", "edibles", "beverages", "concentrates", "tinctures", "topicals"
]

INV_NAME_ALIASES = ["product", "productname", "item", "itemname", "name", "skuname", "product name", "product_name", "title"]
INV_CAT_ALIASES = ["category", "subcategory", "productcategory", "department", "mastercategory", "product category"]
INV_QTY_ALIASES = ["available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand", "instock", "current quantity"]
INV_SKU_ALIASES = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
INV_BATCH_ALIASES = ["batch", "batchnumber", "batch number", "lot", "lotnumber", "lot number", "batchid", "packageid"]
INV_COST_ALIASES = ["cost", "unitcost", "unit cost", "cogs", "costprice", "wholesale", "wholesale price"]
INV_RETAIL_PRICE_ALIASES = ["medprice", "med price", "retail", "retailprice", "retail price", "msrp"]
INV_STRAIN_TYPE_ALIASES = ["straintype", "strain type", "strain", "ecommstraintype", "producttype"]
INV_BRAND_ALIASES = ["brand", "brandname", "brand name", "vendor", "vendorname", "vendor name", "manufacturer", "producer"]
INV_EXPIRY_ALIASES = ["expirationdate", "expiration date", "expiry", "expirydate", "expiry date", "bestby", "best by", "expdate"]

SALES_NAME_ALIASES = ["product", "productname", "product title", "producttitle", "productid", "name", "item", "itemname", "skuname", "description", "product name"]
SALES_QTY_ALIASES = ["quantitysold", "quantity sold", "qtysold", "qty sold", "itemsold", "items sold", "unitssold", "units sold", "quantity", "qty"]
SALES_CAT_ALIASES = ["mastercategory", "category", "master_category", "productcategory", "product category", "department", "subcategory"]
SALES_REV_ALIASES = ["netsales", "net sales", "sales", "totalsales", "total sales", "revenue", "grosssales", "gross sales"]


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


def _normalize_category(raw):
    if pd.isna(raw) or raw is None:
        return "unknown"
    s = str(raw).lower().strip()
    if not s:
        return "unknown"
    if any(k in s for k in ["flower", "bud", "cannabis flower"]):
        return "flower"
    if any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint"]):
        return "pre rolls"
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        return "vapes"
    if any(k in s for k in ["edible", "gummy", "gummies", "chocolate", "chew", "cookies"]):
        return "edibles"
    if any(k in s for k in ["beverage", "drink", "shot"]):
        return "beverages"
    if any(k in s for k in ["concentrate", "wax", "shatter", "crumble", "resin", "rosin", "dab", "rso"]):
        return "concentrates"
    if any(k in s for k in ["tincture", "drops", "sublingual"]):
        return "tinctures"
    if any(k in s for k in ["topical", "lotion", "cream", "salve", "balm"]):
        return "topicals"
    return s


def _extract_size(text, context=None):
    if pd.isna(text) or text is None:
        return "unspecified"
    s = str(text).lower().strip()
    mg = re.search(r"(\d+(\.\d+)?\s?mg)\b", s)
    if mg:
        return mg.group(1).replace(" ", "")
    g = re.search(r"((?:\d+\.?\d*|\.\d+)\s?(g|oz))\b", s)
    if g:
        val = g.group(1).replace(" ", "").lower()
        if val in ["1oz", "1.0oz", "28g", "28.0g"]:
            return "28g"
        return val
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        if re.search(r"\b0\.5\b|\b\.5\b", s):
            return "0.5g"
    return "unspecified"


def _stack_parts(*parts):
    parts_clean = [p.strip() for p in parts if p and str(p).strip() and str(p).strip() != "unspecified"]
    if not parts_clean:
        return "unspecified"
    return " ".join(parts_clean)


def _extract_strain_type(name, subcat):
    s = str(name).lower().strip()
    cat = str(subcat).lower().strip()
    base = "unspecified"
    if "indica" in s:
        base = "indica"
    elif "sativa" in s:
        base = "sativa"
    elif "hybrid" in s:
        base = "hybrid"
    elif "cbd" in s:
        base = "cbd"
    flower_bucket = None
    if "flower" in cat:
        if "super shake" in s:
            flower_bucket = "super shake"
        elif "shake" in s:
            flower_bucket = "shake"
        elif any(k in s for k in ["small buds", "smalls", "small bud"]):
            flower_bucket = "small buds"
        elif "popcorn" in s:
            flower_bucket = "popcorn"
    vape_flag = ("vape" in cat) or any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"])
    oil = None
    if vape_flag:
        if any(k in s for k in ["liquid live resin", "live resin", "llr"]):
            oil = "live resin"
        elif "cured resin" in s:
            oil = "cured resin"
        elif "rosin" in s:
            oil = "rosin"
        elif any(k in s for k in ["distillate", "disty"]):
            oil = "distillate"
        if "disposable" in s:
            oil = _stack_parts(oil, "disposable")
    if "flower" in cat:
        return _stack_parts(base, flower_bucket)
    if vape_flag:
        return _stack_parts(base, oil)
    return base


def _deduplicate_inventory(inv_df: pd.DataFrame):
    if inv_df is None or inv_df.empty:
        return inv_df
    if "batch" not in inv_df.columns:
        return inv_df
    df = inv_df.copy()
    df["batch"] = df["batch"].fillna("").astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "None": np.nan})
    has_batch = df["batch"].notna()
    if not has_batch.any():
        return df
    with_batch = df[has_batch].copy()
    without_batch = df[~has_batch].copy()
    agg_map = {"onhandunits": "sum"}
    for c in ["subcategory", "sku", "itemname", "unit_cost", "retail_price", "brand_vendor", "expiration_date"]:
        if c in with_batch.columns and c not in ["itemname", "batch"]:
            agg_map[c] = "first" if c != "expiration_date" else "min"
    deduped = with_batch.groupby(["itemname", "batch"], dropna=False, as_index=False).agg(agg_map)
    return pd.concat([deduped, without_batch], ignore_index=True)


def _build_forecast(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, doh_threshold: int, velocity_adjustment: float, sales_period_days: int):
    inv_df = inv_raw_df.copy()
    sales_raw = sales_raw_df.copy()
    inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()
    sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()

    name_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_NAME_ALIASES])
    cat_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_CAT_ALIASES])
    qty_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_QTY_ALIASES])
    sku_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_SKU_ALIASES])
    batch_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_BATCH_ALIASES])
    cost_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_COST_ALIASES])
    retail_price_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])
    strain_type_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_STRAIN_TYPE_ALIASES])
    brand_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_BRAND_ALIASES])
    expiry_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_EXPIRY_ALIASES])
    if not (name_col and cat_col and qty_col):
        raise ValueError("Could not detect inventory product / category / on-hand columns.")

    rename_map = {name_col: "itemname", cat_col: "subcategory", qty_col: "onhandunits"}
    if sku_col: rename_map[sku_col] = "sku"
    if batch_col: rename_map[batch_col] = "batch"
    if strain_type_col: rename_map[strain_type_col] = "_explicit_strain_type"
    if retail_price_col: rename_map[retail_price_col] = "retail_price"
    if cost_col: rename_map[cost_col] = "unit_cost"
    if brand_col: rename_map[brand_col] = "brand_vendor"
    if expiry_col: rename_map[expiry_col] = "expiration_date"
    inv_df = inv_df.rename(columns=rename_map)
    inv_df["itemname"] = inv_df["itemname"].astype(str).str.strip()
    inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)
    if "unit_cost" in inv_df.columns:
        inv_df["unit_cost"] = _parse_currency_to_float(inv_df["unit_cost"]).fillna(0)
    if "retail_price" in inv_df.columns:
        inv_df["retail_price"] = _parse_currency_to_float(inv_df["retail_price"]).fillna(0)
    if "expiration_date" in inv_df.columns:
        inv_df["expiration_date"] = pd.to_datetime(inv_df["expiration_date"], errors="coerce")
    inv_df = _deduplicate_inventory(inv_df)
    inv_df["subcategory"] = inv_df["subcategory"].apply(_normalize_category)
    inv_df["strain_type"] = inv_df.apply(lambda x: _extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
    if "_explicit_strain_type" in inv_df.columns:
        explicit = inv_df["_explicit_strain_type"].astype(str).str.strip().str.lower()
        valid = explicit.isin(["indica", "sativa", "hybrid", "cbd"])
        inv_df.loc[valid, "strain_type"] = explicit[valid]
        inv_df = inv_df.drop(columns=["_explicit_strain_type"])
    inv_df["packagesize"] = inv_df.apply(lambda x: _extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
    inv_df["product_name"] = inv_df["itemname"]

    sales_name_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_NAME_ALIASES])
    sales_qty_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_QTY_ALIASES])
    sales_cat_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_CAT_ALIASES])
    sales_rev_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_REV_ALIASES])
    if not (sales_name_col and sales_qty_col and sales_cat_col):
        raise ValueError("Could not detect sales product / quantity / category columns.")

    sales_raw = sales_raw.rename(columns={sales_name_col: "product_name", sales_qty_col: "unitssold", sales_cat_col: "mastercategory"})
    if sales_rev_col:
        sales_raw = sales_raw.rename(columns={sales_rev_col: "revenue"})
    sales_raw["product_name"] = sales_raw["product_name"].astype(str).str.strip()
    sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0)
    sales_raw["mastercategory"] = sales_raw["mastercategory"].astype(str).str.strip().apply(_normalize_category)
    if "revenue" in sales_raw.columns:
        sales_raw["revenue"] = pd.to_numeric(sales_raw["revenue"], errors="coerce").fillna(0)
    sales_df = sales_raw[~sales_raw["mastercategory"].astype(str).str.contains("accessor", na=False) & (sales_raw["mastercategory"] != "all")].copy()
    sales_df["packagesize"] = sales_df.apply(lambda r: _extract_size(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)
    sales_df["strain_type"] = sales_df.apply(lambda r: _extract_strain_type(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)

    inv_summary = inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"].sum().reset_index()
    if "unit_cost" in inv_df.columns:
        inv_summary = inv_summary.merge(inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["unit_cost"].median().reset_index(), on=["subcategory", "strain_type", "packagesize"], how="left")
    if "retail_price" in inv_df.columns:
        inv_summary = inv_summary.merge(inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["retail_price"].median().reset_index(), on=["subcategory", "strain_type", "packagesize"], how="left")

    inv_product = inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)["onhandunits"].sum().reset_index()
    for c in ["brand_vendor", "expiration_date", "sku"]:
        if c in inv_df.columns:
            inv_product = inv_product.merge(inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)[c].first().reset_index(), on=["subcategory", "product_name", "strain_type", "packagesize"], how="left")
    if "unit_cost" in inv_df.columns:
        inv_product = inv_product.merge(inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)["unit_cost"].median().reset_index(), on=["subcategory", "product_name", "strain_type", "packagesize"], how="left")
    if "retail_price" in inv_df.columns:
        inv_product = inv_product.merge(inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)["retail_price"].median().reset_index(), on=["subcategory", "product_name", "strain_type", "packagesize"], how="left")

    sales_summary = sales_df.groupby(["mastercategory", "packagesize"], dropna=False)["unitssold"].sum().reset_index()
    sales_summary["avgunitsperday"] = (sales_summary["unitssold"] / max(int(sales_period_days), 1)) * float(velocity_adjustment)

    sales_product = sales_df.groupby(["mastercategory", "product_name", "strain_type", "packagesize"], dropna=False)["unitssold"].sum().reset_index()
    sales_product["avgunitsperday"] = (sales_product["unitssold"] / max(int(sales_period_days), 1)) * float(velocity_adjustment)

    detail = pd.merge(inv_summary, sales_summary, how="left", left_on=["subcategory", "packagesize"], right_on=["mastercategory", "packagesize"]).fillna(0)
    detail_product = pd.merge(inv_product, sales_product, how="left", left_on=["subcategory", "product_name", "strain_type", "packagesize"], right_on=["mastercategory", "product_name", "strain_type", "packagesize"]).fillna(0)

    detail["daysonhand"] = np.where(detail["avgunitsperday"] > 0, detail["onhandunits"] / detail["avgunitsperday"], 0)
    detail["daysonhand"] = detail["daysonhand"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)
    detail["reorderqty"] = np.where(detail["daysonhand"] < doh_threshold, np.ceil((doh_threshold - detail["daysonhand"]) * detail["avgunitsperday"]), 0).astype(int)

    def tag(row):
        if row["daysonhand"] <= 7 and row["avgunitsperday"] > 0:
            return "1 – Reorder ASAP"
        if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0:
            return "2 – Watch Closely"
        if row["avgunitsperday"] == 0:
            return "4 – Dead Item"
        return "3 – Comfortable Cover"
    detail["reorderpriority"] = detail.apply(tag, axis=1)

    detail_product["avgunitsperday"] = pd.to_numeric(detail_product["avgunitsperday"], errors="coerce").fillna(0)
    detail_product["onhandunits"] = pd.to_numeric(detail_product["onhandunits"], errors="coerce").fillna(0)
    detail_product["daysonhand"] = np.where(detail_product["avgunitsperday"] > 0, detail_product["onhandunits"] / detail_product["avgunitsperday"], 0)
    detail_product["daysonhand"] = detail_product["daysonhand"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)

    return detail, detail_product, inv_df, sales_df


def _build_forecast_export_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Forecast")
    buf.seek(0)
    return buf.read()


def render_buyer_full_view():
    render_section_header(
        "Buyer Operations",
        "Full buyer workflow in the modular app: controls, DOS, forecast, product rows, SKU buyer view, exports, and Doobie brief.",
    )

    inv_raw_df = st.session_state.get(INV_RAW)
    sales_raw_df = st.session_state.get(SALES_RAW)
    if not isinstance(inv_raw_df, pd.DataFrame) or not isinstance(sales_raw_df, pd.DataFrame):
        st.warning("Inventory and Product Sales uploads are required. Use Inventory Prep first.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        doh_threshold = int(st.number_input("Target Days on Hand", 1, 120, 21, key="buyer_full_doh"))
    with c2:
        velocity_adjustment = float(st.number_input("Velocity Adjustment", 0.01, 5.0, 0.5, key="buyer_full_velocity"))
    with c3:
        sales_period_days = int(st.slider("Days in Sales Period", 7, 120, 60, key="buyer_full_sales_days"))

    try:
        detail_df, detail_product_df, inv_df, sales_df = _build_forecast(
            inv_raw_df=inv_raw_df,
            sales_raw_df=sales_raw_df,
            doh_threshold=doh_threshold,
            velocity_adjustment=velocity_adjustment,
            sales_period_days=sales_period_days,
        )
        st.session_state["detail_cached_df"] = detail_df.copy()
        st.session_state[BUYER_READY] = detail_product_df.copy()
        st.session_state["detail_product_cached_df"] = detail_product_df.copy()
    except Exception as exc:
        st.error(f"Could not build buyer forecast pipeline: {exc}")
        return

    total_units = int(pd.to_numeric(detail_df.get("unitssold", 0), errors="coerce").fillna(0).sum())
    reorder_asap = int((detail_df.get("reorderpriority", pd.Series(dtype=str)) == "1 – Reorder ASAP").sum())
    tracked_products = len(detail_product_df)
    cat_count = detail_df["subcategory"].nunique() if "subcategory" in detail_df.columns else 0

    top = st.columns(4)
    with top[0]:
        render_metric_card("Units Sold", f"{total_units:,}", "Granular size-level units sold")
    with top[1]:
        render_metric_card("Reorder ASAP", f"{reorder_asap:,}", "Lines requiring action")
    with top[2]:
        render_metric_card("Tracked Products", f"{tracked_products:,}", "Product-level rows")
    with top[3]:
        render_metric_card("Categories", f"{cat_count:,}", "Active buyer categories")

    tabs = st.tabs([
        "Category DOS",
        "Forecast Table",
        "Product Rows",
        "SKU Buyer View",
        "Doobie Buyer Brief",
    ])

    with tabs[0]:
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
        dp = detail_product_df[["subcategory", "product_name", "unitssold"]].copy()
        dp["unitssold"] = pd.to_numeric(dp["unitssold"], errors="coerce").fillna(0)
        top_products = (
            dp.sort_values("unitssold", ascending=False)
            .groupby("subcategory", dropna=False, sort=False)["product_name"]
            .apply(lambda x: ", ".join(x.astype(str).head(5).tolist()))
            .reset_index().rename(columns={"product_name": "top_products"})
        )
        product_count = (
            dp.groupby("subcategory", dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name": "product_count"})
        )
        cat_quick = cat_quick.merge(top_products, on="subcategory", how="left").merge(product_count, on="subcategory", how="left")
        cat_quick["product_count"] = cat_quick["product_count"].fillna(0).astype(int)
        cat_quick["top_products"] = cat_quick["top_products"].fillna("")
        def cat_sort_key(c):
            c_low = str(c).lower()
            if c_low in REB_CATEGORIES:
                return (REB_CATEGORIES.index(c_low), c_low)
            return (len(REB_CATEGORIES), c_low)
        cat_quick = cat_quick.sort_values("subcategory", key=lambda s: s.map(lambda x: cat_sort_key(x)))
        st.dataframe(cat_quick[["subcategory", "category_dos", "reorder_lines", "product_count", "top_products"]], use_container_width=True, hide_index=True)

    with tabs[1]:
        selected_cats = st.multiselect(
            "Visible Categories",
            sorted(detail_df["subcategory"].dropna().unique().tolist(), key=lambda x: (REB_CATEGORIES.index(str(x).lower()) if str(x).lower() in REB_CATEGORIES else 999, str(x).lower())),
            default=sorted(detail_df["subcategory"].dropna().unique().tolist(), key=lambda x: (REB_CATEGORIES.index(str(x).lower()) if str(x).lower() in REB_CATEGORIES else 999, str(x).lower())),
            key="buyer_full_categories",
        )
        show_only_reorder = st.toggle("Only Reorder ASAP", value=False, key="buyer_full_only_reorder")
        forecast_view = detail_df[detail_df["subcategory"].isin(selected_cats)].copy()
        if show_only_reorder:
            forecast_view = forecast_view[forecast_view["reorderpriority"] == "1 – Reorder ASAP"]
        prod_ctx = (
            detail_product_df[["subcategory", "product_name", "strain_type", "packagesize", "unitssold"]]
            .assign(unitssold=lambda d: pd.to_numeric(d["unitssold"], errors="coerce").fillna(0))
            .sort_values("unitssold", ascending=False)
            .groupby(["subcategory", "strain_type", "packagesize"], dropna=False, sort=False)["product_name"]
            .apply(lambda x: ", ".join(x.astype(str).head(5).tolist()))
            .reset_index().rename(columns={"product_name": "top_products"})
        )
        prod_count = (
            detail_product_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["product_name"]
            .nunique().reset_index().rename(columns={"product_name": "product_count"})
        )
        forecast_view = forecast_view.merge(prod_ctx, on=["subcategory", "strain_type", "packagesize"], how="left").merge(prod_count, on=["subcategory", "strain_type", "packagesize"], how="left")
        forecast_view["product_count"] = forecast_view["product_count"].fillna(0).astype(int)
        forecast_view["top_products"] = forecast_view["top_products"].fillna("")
        display_cols = [c for c in ["top_products", "mastercategory", "subcategory", "strain_type", "packagesize", "onhandunits", "unitssold", "avgunitsperday", "daysonhand", "reorderqty", "reorderpriority", "product_count"] if c in forecast_view.columns]
        st.dataframe(forecast_view[display_cols], use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Export Forecast Table (Excel)",
            data=_build_forecast_export_bytes(forecast_view[display_cols]),
            file_name="forecast_table.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="buyer_full_forecast_export",
        )

    with tabs[2]:
        show_limit_caption = len(detail_product_df) > PRODUCT_TABLE_DISPLAY_LIMIT
        dpv = detail_product_df.copy()
        if show_limit_caption:
            st.caption(f"⚠️ Showing top {PRODUCT_TABLE_DISPLAY_LIMIT} rows by units sold.")
            dpv = dpv.sort_values("unitssold", ascending=False).head(PRODUCT_TABLE_DISPLAY_LIMIT)
        prod_cols = [c for c in ["product_name", "subcategory", "strain_type", "packagesize", "brand_vendor", "sku", "onhandunits", "unitssold", "avgunitsperday", "daysonhand", "expiration_date"] if c in dpv.columns]
        st.dataframe(dpv[prod_cols], use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Download Product-Level Table (Excel)",
            data=_build_forecast_export_bytes(dpv[prod_cols]),
            file_name="product_level_forecast.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="buyer_full_product_export",
        )

    with tabs[3]:
        vel_window = st.selectbox("Velocity window", [28, 56, 84], index=1, key="buyer_full_sku_vel")
        sku_df = detail_product_df.copy()
        # rebuild SKU-wide view from raw files for parity
        sku_df = _build_forecast(inv_raw_df, sales_raw_df, doh_threshold=doh_threshold, velocity_adjustment=velocity_adjustment, sales_period_days=vel_window)[1]
        # summarize to one line per product/SKU style
        view = sku_df.copy()
        if "unit_cost" in view.columns:
            view["dollars_on_hand"] = view["onhandunits"] * pd.to_numeric(view["unit_cost"], errors="coerce").fillna(0)
        if "retail_price" in view.columns:
            view["retail_dollars_on_hand"] = view["onhandunits"] * pd.to_numeric(view["retail_price"], errors="coerce").fillna(0)
        if "expiration_date" in view.columns:
            today = pd.Timestamp.today().normalize()
            view["days_to_expire"] = (pd.to_datetime(view["expiration_date"], errors="coerce") - today).dt.days
        view["days_of_supply"] = np.where(
            pd.to_numeric(view["avgunitsperday"], errors="coerce").fillna(0) > 0,
            pd.to_numeric(view["onhandunits"], errors="coerce").fillna(0) / pd.to_numeric(view["avgunitsperday"], errors="coerce").replace(0, np.nan),
            UNKNOWN_DAYS_OF_SUPPLY,
        )
        view["weeks_of_supply"] = (view["days_of_supply"] / 7).round(1)
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
        view["status"] = view.apply(status, axis=1)
        cols_order = [c for c in ["sku", "product_name", "brand_vendor", "subcategory", "onhandunits", "avgunitsperday", "days_of_supply", "weeks_of_supply", "dollars_on_hand", "retail_dollars_on_hand", "expiration_date", "days_to_expire", "status"] if c in view.columns]
        t1, t2, t3, t4 = st.tabs(["📦 All Inventory", "🔴 Reorder", "🟠 Overstock", "⚠️ Expiring"])
        with t1:
            st.dataframe(view[cols_order], use_container_width=True, hide_index=True)
        with t2:
            st.dataframe(view[view["days_of_supply"] <= INVENTORY_REORDER_DOH_THRESHOLD][cols_order], use_container_width=True, hide_index=True)
        with t3:
            st.dataframe(view[view["days_of_supply"] >= INVENTORY_OVERSTOCK_DOH_THRESHOLD][cols_order], use_container_width=True, hide_index=True)
        with t4:
            if "days_to_expire" in view.columns:
                st.dataframe(view[view["days_to_expire"].notna() & (view["days_to_expire"] < INVENTORY_EXPIRING_SOON_DAYS)][cols_order], use_container_width=True, hide_index=True)
            else:
                st.info("No expiration date column detected in the inventory file.")

    with tabs[4]:
        st.caption("Doobie replaces the legacy buyer AI while preserving the buyer outputs above.")
        if st.button("Generate Doobie Buyer Brief", key="buyer_full_doobie_brief"):
            run_buyer_doobie(detail_product_df, state="MA")
