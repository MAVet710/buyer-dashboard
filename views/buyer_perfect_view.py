import re
from difflib import SequenceMatcher
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

from core.session_keys import INV_RAW, SALES_RAW, BUYER_READY
from doobie_panels import run_buyer_doobie
from ui.components import render_metric_card, render_section_header
from buyer_inventory_normalization import ensure_inventory_derived_fields, fill_blank_with, resolve_itemname_series

UNKNOWN_DAYS_OF_SUPPLY = 999
PRODUCT_TABLE_DISPLAY_LIMIT = 2000
INVENTORY_REORDER_DOH_THRESHOLD = 21
INVENTORY_OVERSTOCK_DOH_THRESHOLD = 90
INVENTORY_EXPIRING_SOON_DAYS = 60
PO_REVIEW_THRESHOLD = 15
VALID_STRAIN_TYPES = frozenset([
    "indica", "sativa", "hybrid", "cbd",
    "indica dominant hybrid", "sativa dominant hybrid",
])
REB_CATEGORIES = [
    "flower", "pre rolls", "vapes", "edibles", "beverages", "concentrates", "tinctures", "topicals",
]

INV_NAME_ALIASES = [
    "product", "productname", "item", "itemname", "name", "skuname", "skuid", "sku", "product name", "product_name", "product title", "title"
]
INV_CAT_ALIASES = [
    "category", "subcategory", "productcategory", "department", "mastercategory", "product category", "cannabis", "product_category", "ecomm category", "ecommcategory"
]
INV_QTY_ALIASES = [
    "available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand", "instock", "currentquantity", "current quantity", "inventoryavailable", "inventory available", "available quantity", "med total", "medtotal", "med sellable", "medsellable"
]
INV_SKU_ALIASES = ["sku", "skuid", "productid", "product_id", "itemid", "item_id"]
INV_BATCH_ALIASES = ["batch", "batchnumber", "batch number", "lot", "lotnumber", "lot number", "batchid", "batch id", "lotid", "lot id", "inventorybatch", "inventory batch", "packageid", "package id"]
INV_COST_ALIASES = ["cost", "unitcost", "unit cost", "cogs", "costprice", "cost price", "wholesale", "wholesaleprice", "wholesale price", "currentprice", "current price"]
INV_RETAIL_PRICE_ALIASES = ["medprice", "med price", "retail", "retailprice", "retail price", "msrp"]
INV_STRAIN_TYPE_ALIASES = ["straintype", "strain type", "strain", "ecommstraintype", "ecomm strain type", "producttype", "product type"]
INV_BRAND_ALIASES = ["brand", "brandname", "brand name", "vendor", "vendorname", "vendor name", "manufacturer", "producer", "supplier"]
INV_EXPIRY_ALIASES = ["expirationdate", "expiration date", "expiry", "expirydate", "expiry date", "bestby", "best by", "bestbydate", "best by date", "usebydate", "use by date", "expires", "exp", "expdate", "exp date"]

SALES_NAME_ALIASES = ["product", "productname", "product title", "producttitle", "productid", "name", "item", "itemname", "skuname", "sku", "description", "product name", "product_name"]
SALES_QTY_ALIASES = ["quantitysold", "quantity sold", "qtysold", "qty sold", "itemsold", "item sold", "items sold", "unitssold", "units sold", "unit sold", "unitsold", "units", "totalunits", "total units", "totalinventorysold", "total inventory sold", "quantity", "qty"]
SALES_CAT_ALIASES = ["mastercategory", "category", "master_category", "productcategory", "product category", "department", "dept", "subcategory", "productcategoryname", "product category name"]
SALES_REV_ALIASES = ["netsales", "net sales", "sales", "totalsales", "total sales", "revenue", "grosssales", "gross sales"]
SALES_SKU_ALIASES = ["sku", "skuid", "productid", "product_id"]


ITEMNAME_SOURCE_ALIASES = [
    "itemname", "product_name", "name", "product", "sku_name", "item", "sku", "title", "skuname"
]


def _resolve_itemname_series(inv_df: pd.DataFrame, detected_name_col: str | None) -> pd.Series:
    return resolve_itemname_series(
        inv_df,
        detected_name_col,
        detect_column=detect_column,
        normalize_col=normalize_col,
        itemname_aliases=ITEMNAME_SOURCE_ALIASES,
    )


def _fill_blank_with(series: pd.Series, fallback: pd.Series | str) -> pd.Series:
    return fill_blank_with(series, fallback)


def _ensure_inventory_derived_fields(inv_df: pd.DataFrame) -> pd.DataFrame:
    return ensure_inventory_derived_fields(
        inv_df,
        normalize_category=normalize_rebelle_category,
        extract_strain_type=extract_strain_type,
        extract_size=extract_size,
        valid_strain_types=VALID_STRAIN_TYPES,
        detect_column=detect_column,
        normalize_col=normalize_col,
        detected_name_col="itemname",
        itemname_aliases=ITEMNAME_SOURCE_ALIASES,
    )

def normalize_col(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def detect_column(columns, aliases):
    norm_map = {normalize_col(c): c for c in columns}
    for alias in aliases:
        if alias in norm_map:
            return norm_map[alias]
    return None


def parse_currency_to_float(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"^\$", "", regex=True)
        .str.replace(",", "", regex=False)
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
    )


def normalize_rebelle_category(raw):
    if pd.isna(raw) or raw is None:
        return "unknown"
    s = str(raw).lower().strip()
    if not s:
        return "unknown"
    if any(k in s for k in ["flower", "bud", "buds", "cannabis flower"]):
        return "flower"
    if any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint", "joints"]):
        return "pre rolls"
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]):
        return "vapes"
    if any(k in s for k in ["edible", "gummy", "gummies", "chocolate", "chew", "cookies"]):
        return "edibles"
    if any(k in s for k in ["beverage", "drink", "drinkable", "shot", "beverages"]):
        return "beverages"
    if any(k in s for k in ["concentrate", "wax", "shatter", "crumble", "resin", "rosin", "dab", "rso"]):
        return "concentrates"
    if any(k in s for k in ["tincture", "tinctures", "drops", "sublingual", "dropper"]):
        return "tinctures"
    if any(k in s for k in ["topical", "lotion", "cream", "salve", "balm"]):
        return "topicals"
    return s


def extract_size(text, context=None):
    if pd.isna(text) or text is None:
        return "unspecified"
    s = str(text).lower().strip()
    if not s:
        return "unspecified"
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


def extract_strain_type(name, subcat):
    if pd.isna(name):
        name = ""
    if pd.isna(subcat):
        subcat = ""
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
    rr_tag = None
    if "flower" in cat:
        if re.search(r"\brise\b", s):
            rr_tag = "rise"
            if base == "unspecified":
                base = "sativa"
        elif re.search(r"\brefresh\b", s):
            rr_tag = "refresh"
            if base == "unspecified":
                base = "hybrid"
        elif re.search(r"\brest\b", s):
            rr_tag = "rest"
            if base == "unspecified":
                base = "indica"
    vape_flag = ("vape" in cat) or any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"])
    preroll_flag = ("pre roll" in cat) or ("pre rolls" in cat) or any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint"])
    flower_bucket = None
    if "flower" in cat:
        if "super shake" in s:
            flower_bucket = "super shake"
        elif re.search(r"\bshake\b", s):
            flower_bucket = "shake"
        elif any(k in s for k in ["small buds", "smalls", "small bud"]):
            flower_bucket = "small buds"
        elif "popcorn" in s:
            flower_bucket = "popcorn"
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
    is_disposable = ("disposable" in s) or ("dispos" in s)
    if vape_flag and is_disposable:
        oil = _stack_parts(oil, "disposable")
    infused = None
    if preroll_flag and "infused" in s:
        infused = "infused"
    edible_form = None
    if "edible" in cat:
        if any(k in s for k in ["gummy", "gummies", "chew", "fruit chew"]):
            edible_form = "gummy"
        elif any(k in s for k in ["chocolate", "choc"]):
            edible_form = "chocolate"
    conc_tag = None
    if "concentrate" in cat and ("rso" in s or "rick simpson" in s):
        conc_tag = "rso"
    if "flower" in cat:
        return _stack_parts(base, flower_bucket, rr_tag)
    if vape_flag:
        return _stack_parts(base, oil)
    if "edible" in cat:
        return _stack_parts(base, edible_form)
    if "concentrate" in cat:
        return _stack_parts(base, conc_tag)
    if preroll_flag:
        return _stack_parts(base, infused)
    return base


def deduplicate_inventory(inv_df):
    if inv_df is None or inv_df.empty:
        return inv_df, 0, "No inventory data to deduplicate."
    original_count = len(inv_df)
    try:
        if "batch" in inv_df.columns:
            inv_df["batch"] = inv_df["batch"].fillna("")
            inv_df["batch"] = inv_df["batch"].astype(str).str.strip()
            inv_df["batch"] = inv_df["batch"].replace({"": np.nan, "nan": np.nan, "NaN": np.nan, "NAN": np.nan, "none": np.nan, "None": np.nan, "NONE": np.nan, "<NA>": np.nan})
            has_batch = inv_df["batch"].notna()
            if has_batch.any():
                inv_with = inv_df[has_batch].copy()
                inv_without = inv_df[~has_batch].copy()
                dedupe_keys = ["itemname", "batch"]
                agg_map = {"onhandunits": "sum"}
                for c in ["subcategory", "sku", "unit_cost", "retail_price", "brand_vendor", "expiration_date"]:
                    if c in inv_with.columns and c not in dedupe_keys:
                        agg_map[c] = "first" if c != "expiration_date" else "min"
                inv_with_deduped = inv_with.groupby(dedupe_keys, dropna=False, as_index=False).agg(agg_map)
                inv_df = pd.concat([inv_with_deduped, inv_without], ignore_index=True)
                deduplicated_count = len(inv_df)
                num_removed = original_count - deduplicated_count
                if num_removed > 0:
                    log_msg = f"✅ Deduplication complete: Consolidated {num_removed} duplicate inventory entries (Product Name + Batch ID). Original: {original_count} rows → Deduplicated: {deduplicated_count} rows"
                else:
                    log_msg = "No duplicate inventory entries found."
                return inv_df, num_removed, log_msg
        return inv_df, 0, "No batch data available for deduplication."
    except Exception as e:
        return inv_df, 0, f"⚠️ Deduplication encountered an error: {str(e)}. Using original data."


def _parse_grams_from_size(size_str):
    s = str(size_str).lower().strip()
    if s == "28g":
        return 28.0
    if s in ("1oz", "1.0oz"):
        return 28.0
    m = re.match(r"^(\d+(\.\d+)?)g$", s)
    if m:
        return float(m.group(1))
    m2 = re.match(r"^(\d+(\.\d+)?)oz$", s)
    if m2:
        return float(m2.group(1)) * 28.0
    return None


def _parse_mg_from_size(size_str):
    s = str(size_str).lower().strip()
    m = re.match(r"^(\d+(\.\d+)?)mg$", s)
    if m:
        return float(m.group(1))
    return None


def _normalize_for_match(text: str) -> str:
    s = re.sub(r"[^\w\s]", "", str(text).lower())
    return re.sub(r"\s+", " ", s).strip()


def _normalize_size_for_match(size: str) -> str:
    return re.sub(r"\s+", "", str(size).lower().strip())


def _build_xref_table(inv_df: pd.DataFrame):
    if inv_df is None or inv_df.empty:
        return None
    agg = inv_df.groupby(["product_name", "packagesize"], dropna=False)["onhandunits"].sum().reset_index().rename(columns={"onhandunits": "onhand_total"})
    agg["norm_name"] = agg["product_name"].apply(_normalize_for_match)
    agg["norm_size"] = agg["packagesize"].apply(_normalize_size_for_match)
    return agg


def _build_export_bytes(df: pd.DataFrame, sheet_name: str = "Export") -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf.read()


def _safe_ratio(a, b):
    try:
        return a / b if b else 0
    except Exception:
        return 0


def _build_buyer_pipeline(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, doh_threshold: int, velocity_adjustment: float, date_diff: int):
    inv_df = inv_raw_df.copy()
    sales_raw = sales_raw_df.copy()
    inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower()
    sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()

    name_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_NAME_ALIASES])
    cat_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_CAT_ALIASES])
    qty_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_QTY_ALIASES])
    sku_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_SKU_ALIASES])
    batch_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_BATCH_ALIASES])
    cost_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_COST_ALIASES])
    retail_price_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])
    strain_type_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_STRAIN_TYPE_ALIASES])
    brand_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_BRAND_ALIASES])
    expiry_col = detect_column(inv_df.columns, [normalize_col(a) for a in INV_EXPIRY_ALIASES])
    if not (name_col and qty_col):
        raise ValueError("Could not auto-detect inventory columns (product and on-hand).")

    rename_map = {name_col: "itemname", qty_col: "onhandunits"}
    if cat_col:
        rename_map[cat_col] = "subcategory"
    inv_df = inv_df.rename(columns=rename_map)
    if sku_col:
        inv_df = inv_df.rename(columns={sku_col: "sku"})
    if batch_col:
        inv_df = inv_df.rename(columns={batch_col: "batch"})
    if strain_type_col:
        inv_df = inv_df.rename(columns={strain_type_col: "_explicit_strain_type"})
    if retail_price_col:
        inv_df = inv_df.rename(columns={retail_price_col: "retail_price"})
        inv_df["retail_price"] = parse_currency_to_float(inv_df["retail_price"])
    if cost_col:
        inv_df = inv_df.rename(columns={cost_col: "unit_cost"})
        inv_df["unit_cost"] = parse_currency_to_float(inv_df["unit_cost"]).fillna(0)
    if brand_col:
        inv_df = inv_df.rename(columns={brand_col: "brand_vendor"})
    if expiry_col:
        inv_df = inv_df.rename(columns={expiry_col: "expiration_date"})
        inv_df["expiration_date"] = pd.to_datetime(inv_df["expiration_date"], errors="coerce")

    inv_df["itemname"] = _resolve_itemname_series(inv_df, "itemname")
    inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)
    inv_df, _, _ = deduplicate_inventory(inv_df)
    inv_df = _ensure_inventory_derived_fields(inv_df)
    inv_df["product_name"] = inv_df["itemname"]

    inv_summary = inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"].sum().reset_index()
    if "unit_cost" in inv_df.columns:
        _cost_summary = inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["unit_cost"].median().reset_index()
        inv_summary = inv_summary.merge(_cost_summary, on=["subcategory", "strain_type", "packagesize"], how="left")
    if "retail_price" in inv_df.columns:
        _retail_summary = inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["retail_price"].median().reset_index()
        inv_summary = inv_summary.merge(_retail_summary, on=["subcategory", "strain_type", "packagesize"], how="left")

    inv_product = inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)["onhandunits"].sum().reset_index()
    for extra_col in ["brand_vendor", "sku", "expiration_date", "unit_cost", "retail_price"]:
        if extra_col in inv_df.columns:
            _extra = inv_df.groupby(["subcategory", "product_name", "strain_type", "packagesize"], dropna=False)[extra_col].first().reset_index()
            inv_product = inv_product.merge(_extra, on=["subcategory", "product_name", "strain_type", "packagesize"], how="left")

    name_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_NAME_ALIASES])
    qty_col_sales = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_QTY_ALIASES])
    mc_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_CAT_ALIASES])
    sales_sku_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_SKU_ALIASES])
    rev_col = detect_column(sales_raw.columns, [normalize_col(a) for a in SALES_REV_ALIASES])
    if not (name_col_sales and qty_col_sales and mc_col):
        raise ValueError("Could not detect required sales columns (name, quantity, category).")

    sales_raw = sales_raw.rename(columns={name_col_sales: "product_name", qty_col_sales: "unitssold", mc_col: "mastercategory"})
    if sales_sku_col:
        sales_raw = sales_raw.rename(columns={sales_sku_col: "sku"})
    if rev_col:
        sales_raw = sales_raw.rename(columns={rev_col: "net_sales"})
    sales_raw["product_name"] = sales_raw["product_name"].astype(str).str.strip()
    sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0)
    if "net_sales" in sales_raw.columns:
        sales_raw["net_sales"] = pd.to_numeric(sales_raw["net_sales"], errors="coerce").fillna(0)
    sales_raw["mastercategory"] = sales_raw["mastercategory"].astype(str).str.strip().apply(normalize_rebelle_category)
    sales_df = sales_raw[~sales_raw["mastercategory"].astype(str).str.contains("accessor", na=False) & (sales_raw["mastercategory"] != "all")].copy()
    sales_df["packagesize"] = sales_df.apply(lambda row: extract_size(row.get("product_name", ""), row.get("mastercategory", "")), axis=1)
    sales_df["strain_type"] = sales_df.apply(lambda row: extract_strain_type(row.get("product_name", ""), row.get("mastercategory", "")), axis=1)
    sales_detail_df = sales_df.drop_duplicates().copy()

    sales_summary = sales_df.groupby(["mastercategory", "packagesize"], dropna=False)["unitssold"].sum().reset_index()
    sales_summary["avgunitsperday"] = (sales_summary["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)
    sales_product = sales_df.groupby(["mastercategory", "product_name", "strain_type", "packagesize"], dropna=False)["unitssold"].sum().reset_index()
    sales_product["avgunitsperday"] = (sales_product["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)

    detail_product = pd.merge(inv_product, sales_product, how="left", left_on=["subcategory", "product_name", "strain_type", "packagesize"], right_on=["mastercategory", "product_name", "strain_type", "packagesize"]).fillna(0)
    detail = pd.merge(inv_summary, sales_summary, how="left", left_on=["subcategory", "packagesize"], right_on=["mastercategory", "packagesize"]).fillna(0)

    flower_mask = detail["subcategory"].astype(str).str.contains("flower", na=False)
    flower_cats = detail.loc[flower_mask, "subcategory"].unique().tolist()
    def estimate_28g_from_flower_sales(cat_name: str):
        direct = sales_df[(sales_df["mastercategory"] == cat_name) & (sales_df["packagesize"] == "28g")]
        if not direct.empty:
            units_28 = float(direct["unitssold"].sum())
            avg_28 = (units_28 / max(int(date_diff), 1)) * float(velocity_adjustment)
            return units_28, avg_28
        cat_sales = sales_df[sales_df["mastercategory"] == cat_name].copy()
        if cat_sales.empty:
            return 0.0, 0.0
        total_grams = 0.0
        for _, r in cat_sales.iterrows():
            grams = _parse_grams_from_size(r.get("packagesize", "unspecified"))
            if grams is None:
                continue
            total_grams += float(r.get("unitssold", 0)) * grams
        if total_grams <= 0:
            return 0.0, 0.0
        est_oz_units = total_grams / 28.0
        avg_oz = (est_oz_units / max(int(date_diff), 1)) * float(velocity_adjustment)
        return float(est_oz_units), float(avg_oz)
    missing_rows = []
    for cat in flower_cats:
        has_28 = ((detail["subcategory"] == cat) & (detail["packagesize"] == "28g")).any()
        if not has_28:
            units_28, avg_28 = estimate_28g_from_flower_sales(cat)
            missing_rows.append({"subcategory": cat, "strain_type": "unspecified", "packagesize": "28g", "onhandunits": 0, "mastercategory": cat, "unitssold": units_28, "avgunitsperday": avg_28})
        else:
            row_mask = (detail["subcategory"] == cat) & (detail["packagesize"] == "28g")
            if row_mask.any():
                cur_avg = float(detail.loc[row_mask, "avgunitsperday"].iloc[0])
                if cur_avg == 0:
                    units_28, avg_28 = estimate_28g_from_flower_sales(cat)
                    if avg_28 > 0:
                        detail.loc[row_mask, "unitssold"] = units_28
                        detail.loc[row_mask, "avgunitsperday"] = avg_28
    if missing_rows:
        detail = pd.concat([detail, pd.DataFrame(missing_rows)], ignore_index=True)

    edibles_mask = detail["subcategory"].astype(str).str.contains("edible", na=False)
    edibles_cats = detail.loc[edibles_mask, "subcategory"].unique().tolist()
    def estimate_500mg_from_edible_sales(cat_name: str):
        direct = sales_df[(sales_df["mastercategory"] == cat_name) & (sales_df["packagesize"] == "500mg")]
        if not direct.empty:
            units_500 = float(direct["unitssold"].sum())
            avg_500 = (units_500 / max(int(date_diff), 1)) * float(velocity_adjustment)
            return units_500, avg_500
        cat_sales = sales_df[sales_df["mastercategory"] == cat_name].copy()
        if cat_sales.empty:
            return 0.0, 0.0
        total_mg = 0.0
        for _, r in cat_sales.iterrows():
            mg = _parse_mg_from_size(r.get("packagesize", "unspecified"))
            if mg is None:
                continue
            total_mg += float(r.get("unitssold", 0)) * mg
        if total_mg <= 0:
            return 0.0, 0.0
        est_500_units = total_mg / 500.0
        avg_500 = (est_500_units / max(int(date_diff), 1)) * float(velocity_adjustment)
        return float(est_500_units), float(avg_500)
    edibles_missing = []
    for cat in edibles_cats:
        has_500 = ((detail["subcategory"] == cat) & (detail["packagesize"] == "500mg")).any()
        if not has_500:
            units_500, avg_500 = estimate_500mg_from_edible_sales(cat)
            edibles_missing.append({"subcategory": cat, "strain_type": "unspecified", "packagesize": "500mg", "onhandunits": 0, "mastercategory": cat, "unitssold": units_500, "avgunitsperday": avg_500})
        else:
            row_mask = (detail["subcategory"] == cat) & (detail["packagesize"] == "500mg")
            if row_mask.any():
                cur_avg = float(detail.loc[row_mask, "avgunitsperday"].iloc[0])
                if cur_avg == 0:
                    units_500, avg_500 = estimate_500mg_from_edible_sales(cat)
                    if avg_500 > 0:
                        detail.loc[row_mask, "unitssold"] = units_500
                        detail.loc[row_mask, "avgunitsperday"] = avg_500
    if edibles_missing:
        detail = pd.concat([detail, pd.DataFrame(edibles_missing)], ignore_index=True)

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

    return detail, detail_product, inv_df, sales_detail_df


def _build_sku_drilldown_table(inv_df, sales_detail_df, cat, size, strain_type, date_diff, velocity_adjustment):
    sd = sales_detail_df[(sales_detail_df["mastercategory"] == cat) & (sales_detail_df["packagesize"] == size)].copy()
    if str(strain_type).lower() != "unspecified":
        sd = sd[sd["strain_type"].astype(str).str.lower() == str(strain_type).lower()]
    if sd.empty:
        return pd.DataFrame(), pd.DataFrame()
    has_batch = "batch_id" in sd.columns
    has_package = "package_id" in sd.columns
    has_net_sales = "net_sales" in sd.columns
    has_sku = "sku" in sd.columns
    group_cols = ["product_name"]
    if has_batch:
        group_cols.append("batch_id")
    if has_package:
        group_cols.append("package_id")
    agg_dict = {"unitssold": "sum"}
    if has_net_sales:
        agg_dict["net_sales"] = "sum"
    if has_sku:
        agg_dict["sku"] = "first"
    sku_df = sd.groupby(group_cols, dropna=False).agg(agg_dict).reset_index()
    sku_df["est_units_per_day"] = (sku_df["unitssold"] / max(int(date_diff), 1)) * float(velocity_adjustment)
    out_cols = ["product_name"]
    if has_batch:
        out_cols.append("batch_id")
    if has_package:
        out_cols.append("package_id")
    out_cols.append("unitssold")
    if has_net_sales:
        out_cols.append("net_sales")
    out_cols.append("est_units_per_day")
    if has_sku:
        out_cols.append("sku")
    sku_df = sku_df[out_cols].sort_values("est_units_per_day", ascending=False).head(50)
    idf = inv_df[(inv_df["subcategory"] == cat) & (inv_df["packagesize"] == size)].copy()
    if str(strain_type).lower() != "unspecified":
        idf = idf[idf["strain_type"].astype(str).str.lower() == str(strain_type).lower()]
    batch_df = pd.DataFrame()
    if not idf.empty and "batch" in idf.columns:
        batch_df = idf.groupby("batch", dropna=False)["onhandunits"].sum().reset_index().rename(columns={"onhandunits": "batch_onhandunits"}).sort_values("batch_onhandunits", ascending=False)
    return sku_df, batch_df


def _build_sku_inventory_buyer_view(inv_df, sales_detail_df, vel_window):
    inv_roll = inv_df.copy()
    agg_map = {"onhandunits": "sum"}
    for c in ["unit_cost", "retail_price", "brand_vendor", "subcategory", "sku", "expiration_date"]:
        if c in inv_roll.columns:
            agg_map[c] = "first" if c != "expiration_date" else "min"
    sku_df = inv_roll.groupby("product_name", dropna=False).agg(agg_map).reset_index().rename(columns={"subcategory": "category"})
    sales = sales_detail_df.copy()
    date_cols = [c for c in sales.columns if "date" in c]
    if date_cols:
        date_col = date_cols[0]
        sales[date_col] = pd.to_datetime(sales[date_col], errors="coerce")
        cutoff = sales[date_col].max() - pd.Timedelta(days=vel_window)
        sales = sales[sales[date_col] >= cutoff].copy()
    vel = sales.groupby("product_name")["unitssold"].sum().reset_index().rename(columns={"unitssold": "total_sold"})
    vel["daily_run_rate"] = vel["total_sold"] / max(vel_window, 1)
    vel["avg_weekly_sales"] = vel["daily_run_rate"] * 7
    sku_df = sku_df.merge(vel, on="product_name", how="left")
    for c in ["total_sold", "daily_run_rate", "avg_weekly_sales"]:
        sku_df[c] = sku_df[c].fillna(0)
    sku_df["days_of_supply"] = np.where(sku_df["daily_run_rate"] > 0, sku_df["onhandunits"] / sku_df["daily_run_rate"], UNKNOWN_DAYS_OF_SUPPLY)
    sku_df["weeks_of_supply"] = (sku_df["days_of_supply"] / 7).round(1)
    if "unit_cost" in sku_df.columns:
        sku_df["dollars_on_hand"] = sku_df["onhandunits"] * pd.to_numeric(sku_df["unit_cost"], errors="coerce").fillna(0)
    if "retail_price" in sku_df.columns:
        sku_df["retail_dollars_on_hand"] = sku_df["onhandunits"] * pd.to_numeric(sku_df["retail_price"], errors="coerce").fillna(0)
    if "expiration_date" in sku_df.columns:
        today = pd.Timestamp.today().normalize()
        sku_df["days_to_expire"] = (pd.to_datetime(sku_df["expiration_date"], errors="coerce") - today).dt.days
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


def _doobie_inventory_check(detail_view, detail_product_df):
    st.caption("Doobie replaces the legacy AI Inventory Check and evaluates the current filtered buyer slice.")
    if st.button("Run Doobie Inventory Check", key="buyer_perfect_doobie_check"):
        payload = detail_product_df.copy()
        if "subcategory" in detail_view.columns and len(detail_view) > 0:
            allowed = detail_view["subcategory"].astype(str).unique().tolist()
            payload = payload[payload["subcategory"].astype(str).isin(allowed)].copy()
        run_buyer_doobie(payload, state="MA")


def render_buyer_perfect_view():
    render_section_header("Buyer Dashboard", "Original buyer workflow ported into the modular app with Doobie replacing legacy AI.")
    inv_raw_df = st.session_state.get(INV_RAW)
    sales_raw_df = st.session_state.get(SALES_RAW)
    if not isinstance(inv_raw_df, pd.DataFrame) or not isinstance(sales_raw_df, pd.DataFrame):
        st.warning("Inventory and Product Sales uploads are required. Use Inventory Prep first.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        doh_threshold = int(st.number_input("Target Days on Hand", 1, 60, 21, key="buyer_perfect_doh"))
    with c2:
        velocity_adjustment = float(st.number_input("Velocity Adjustment", 0.01, 5.0, 0.5, key="buyer_perfect_velocity"))
    with c3:
        date_diff = int(st.slider("Days in Sales Period", 7, 120, 60, key="buyer_perfect_days"))

    try:
        detail, detail_product, inv_df, sales_detail_df = _build_buyer_pipeline(inv_raw_df, sales_raw_df, doh_threshold, velocity_adjustment, date_diff)
    except Exception as exc:
        st.error(f"Could not build buyer pipeline: {exc}")
        return

    st.session_state["detail_cached_df"] = detail.copy()
    st.session_state[BUYER_READY] = detail_product.copy()
    st.session_state["detail_product_cached_df"] = detail_product.copy()

    total_units = int(pd.to_numeric(detail["unitssold"], errors="coerce").fillna(0).sum())
    reorder_asap = int((detail["reorderpriority"] == "1 – Reorder ASAP").sum())
    if "buyer_metric_filter" not in st.session_state:
        st.session_state["buyer_metric_filter"] = "All"

    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Units Sold (Granular Size-Level): {total_units}", key="buyer_perfect_units_btn"):
            st.session_state["buyer_metric_filter"] = "All"
    with col2:
        if st.button(f"Reorder ASAP (Lines): {reorder_asap}", key="buyer_perfect_reorder_btn"):
            st.session_state["buyer_metric_filter"] = "Reorder ASAP"

    if st.session_state["buyer_metric_filter"] == "Reorder ASAP":
        detail_view = detail[detail["reorderpriority"] == "1 – Reorder ASAP"].copy()
    else:
        detail_view = detail.copy()

    _dp = detail_product[["subcategory", "product_name", "strain_type", "packagesize", "unitssold"]].copy()
    _dp["unitssold"] = pd.to_numeric(_dp["unitssold"], errors="coerce").fillna(0)
    _dp_sorted = _dp.sort_values("unitssold", ascending=False)
    _top_products = _dp_sorted.groupby(["subcategory", "strain_type", "packagesize"], dropna=False, sort=False)["product_name"].apply(lambda x: ", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name": "top_products"})
    _product_counts = _dp.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name": "product_count"})
    _prod_ctx_df = _top_products.merge(_product_counts, on=["subcategory", "strain_type", "packagesize"], how="left")
    detail_view = detail_view.merge(_prod_ctx_df, on=["subcategory", "strain_type", "packagesize"], how="left")
    detail_view["product_count"] = detail_view["product_count"].fillna(0).astype(int)
    detail_view["top_products"] = detail_view["top_products"].fillna("")

    st.markdown(f"*Current filter:* **{st.session_state['buyer_metric_filter']}**")

    all_cats = sorted(detail_view["subcategory"].unique(), key=lambda c: (REB_CATEGORIES.index(str(c).lower()) if str(c).lower() in REB_CATEGORIES else len(REB_CATEGORIES), str(c).lower()))
    selected_cats = st.multiselect("Visible Categories", all_cats, default=all_cats, key="buyer_perfect_visible_cats")
    detail_view = detail_view[detail_view["subcategory"].isin(selected_cats)]
    show_product_rows = st.checkbox("Show product-level rows", value=False, key="buyer_perfect_show_products")

    top = st.columns(4)
    with top[0]:
        render_metric_card("Tracked Categories", f"{detail_view['subcategory'].nunique():,}")
    with top[1]:
        render_metric_card("Forecast Rows", f"{len(detail_view):,}")
    with top[2]:
        render_metric_card("Reorder ASAP", f"{int((detail_view['reorderpriority'] == '1 – Reorder ASAP').sum()):,}")
    with top[3]:
        render_metric_card("Product Rows", f"{len(detail_product):,}")

    cat_quick = detail_view.groupby("subcategory", dropna=False).agg(onhandunits=("onhandunits", "sum"), avgunitsperday=("avgunitsperday", "sum"), reorder_lines=("reorderpriority", lambda x: int((x == "1 – Reorder ASAP").sum()))).reset_index()
    cat_quick["category_dos"] = np.where(cat_quick["avgunitsperday"] > 0, cat_quick["onhandunits"] / cat_quick["avgunitsperday"], 0)
    cat_quick["category_dos"] = cat_quick["category_dos"].replace([np.inf, -np.inf], 0).fillna(0).astype(int)
    _dp_cat = detail_product[["subcategory", "product_name", "unitssold"]].copy()
    _dp_cat["unitssold"] = pd.to_numeric(_dp_cat["unitssold"], errors="coerce").fillna(0)
    _cat_top = _dp_cat.sort_values("unitssold", ascending=False).groupby("subcategory", dropna=False, sort=False)["product_name"].apply(lambda x: ", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name": "top_products"})
    _cat_count = _dp_cat.groupby("subcategory", dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name": "product_count"})
    cat_quick = cat_quick.merge(_cat_top, on="subcategory", how="left").merge(_cat_count, on="subcategory", how="left")
    cat_quick["product_count"] = cat_quick["product_count"].fillna(0).astype(int)
    cat_quick["top_products"] = cat_quick["top_products"].fillna("")
    st.markdown("### Category DOS (at a glance)")
    st.dataframe(cat_quick[["subcategory", "category_dos", "reorder_lines", "product_count", "top_products"]].sort_values(["reorder_lines", "category_dos"], ascending=[False, True]), use_container_width=True, hide_index=True)

    st.markdown("### Forecast Table")
    display_cols = [c for c in ["top_products", "mastercategory", "subcategory", "strain_type", "packagesize", "onhandunits", "unitssold", "avgunitsperday", "daysonhand", "reorderqty", "reorderpriority", "product_count"] if c in detail_view.columns]
    st.download_button("📥 Export Forecast Table (Excel)", data=_build_export_bytes(detail_view[display_cols], "Forecast"), file_name="forecast_table.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="buyer_perfect_export_forecast")
    st.dataframe(detail_view[display_cols], use_container_width=True, hide_index=True)

    for cat in sorted(detail_view["subcategory"].unique(), key=lambda c: (REB_CATEGORIES.index(str(c).lower()) if str(c).lower() in REB_CATEGORIES else len(REB_CATEGORIES), str(c).lower())):
        group = detail_view[detail_view["subcategory"] == cat].copy()
        with st.expander(str(cat).title()):
            denom = float(group["avgunitsperday"].sum()) if len(group) else 0.0
            cat_dos = int(_safe_ratio(float(group["onhandunits"].sum()), denom)) if denom > 0 else 0
            st.markdown(f"**Category DOS:** {cat_dos} days")
            st.dataframe(group[display_cols], use_container_width=True, hide_index=True)
            flagged = group[group["reorderpriority"] == "1 – Reorder ASAP"].copy()
            if not flagged.empty:
                st.markdown("#### 🔎 Flagged Reorder Lines — View SKUs (Weighted by Velocity)")
                for _, r in flagged.iterrows():
                    row_label = f"{r.get('strain_type','unspecified')} • {r.get('packagesize','unspecified')} • Reorder Qty: {int(r.get('reorderqty',0))}"
                    with st.expander(f"View SKUs — {row_label}", expanded=False):
                        sku_df_out, batch_df_out = _build_sku_drilldown_table(inv_df, sales_detail_df, cat=r.get("subcategory"), size=r.get("packagesize"), strain_type=r.get("strain_type"), date_diff=date_diff, velocity_adjustment=velocity_adjustment)
                        if sku_df_out.empty:
                            st.info("No matching SKU-level sales rows found for this slice.")
                        else:
                            st.dataframe(sku_df_out, use_container_width=True, hide_index=True)
                        if not batch_df_out.empty:
                            st.markdown("##### 🧬 Batch / Lot Breakdown (On-Hand)")
                            st.dataframe(batch_df_out, use_container_width=True, hide_index=True)

    if show_product_rows and not detail_product.empty:
        st.markdown("### 📦 Product-Level Rows")
        dpv = detail_product[detail_product["subcategory"].isin(selected_cats)].copy()
        dpv["unitssold"] = pd.to_numeric(dpv["unitssold"], errors="coerce").fillna(0)
        dpv["onhandunits"] = pd.to_numeric(dpv["onhandunits"], errors="coerce").fillna(0)
        if len(dpv) > PRODUCT_TABLE_DISPLAY_LIMIT:
            st.caption(f"⚠️ Showing top {PRODUCT_TABLE_DISPLAY_LIMIT} rows by units sold. Download below for full data.")
            dpv = dpv.sort_values("unitssold", ascending=False).head(PRODUCT_TABLE_DISPLAY_LIMIT)
        prod_display_cols = [c for c in ["product_name", "subcategory", "strain_type", "packagesize", "brand_vendor", "sku", "onhandunits", "unitssold", "avgunitsperday", "daysonhand", "expiration_date"] if c in dpv.columns]
        st.dataframe(dpv[prod_display_cols], use_container_width=True, hide_index=True)
        st.download_button("📥 Download Product-Level Table (Excel)", data=_build_export_bytes(dpv[prod_display_cols], "ProductLevel"), file_name="product_level_forecast.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="buyer_perfect_export_product")

    st.markdown("### 📋 SKU Inventory Buyer View")
    vel_window = st.selectbox("Velocity window", [28, 56, 84], index=1, key="buyer_perfect_sku_vel")
    buyer_view_df = _build_sku_inventory_buyer_view(inv_df, sales_detail_df, vel_window)
    _xref = _build_xref_table(inv_df)
    if _xref is not None:
        st.caption("Inventory cross-reference is active for PO-related buyer review.")
    cols_order = [c for c in ["sku", "product_name", "brand_vendor", "category", "onhandunits", "avg_weekly_sales", "days_of_supply", "weeks_of_supply", "dollars_on_hand", "retail_dollars_on_hand", "expiration_date", "days_to_expire", "status"] if c in buyer_view_df.columns]
    t1, t2, t3, t4 = st.tabs(["📦 All Inventory", "🔴 Reorder", "🟠 Overstock", "⚠️ Expiring"])
    with t1:
        st.dataframe(buyer_view_df[cols_order], use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(buyer_view_df[buyer_view_df["days_of_supply"] <= INVENTORY_REORDER_DOH_THRESHOLD][cols_order], use_container_width=True, hide_index=True)
    with t3:
        st.dataframe(buyer_view_df[buyer_view_df["days_of_supply"] >= INVENTORY_OVERSTOCK_DOH_THRESHOLD][cols_order], use_container_width=True, hide_index=True)
    with t4:
        if "days_to_expire" in buyer_view_df.columns:
            st.dataframe(buyer_view_df[buyer_view_df["days_to_expire"].notna() & (buyer_view_df["days_to_expire"] < INVENTORY_EXPIRING_SOON_DAYS)][cols_order], use_container_width=True, hide_index=True)
        else:
            st.info("No expiration date column detected in the inventory file.")

    st.markdown("### 🤖 Doobie Inventory Check")
    _doobie_inventory_check(detail_view, detail_product)

    st.markdown("### 🧠 Doobie Buyer Brief")
    if st.button("Generate Doobie Buyer Brief", key="buyer_perfect_brief"):
        run_buyer_doobie(detail_product, state="MA")
