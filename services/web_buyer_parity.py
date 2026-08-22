"""UI-independent Buyer Dash parity calculations used by the React/FastAPI stack.

The formulas, thresholds, aliases, and table shapes in this module intentionally
mirror ``views/buyer_full_view.py`` / ``views/buyer_parity_view.py``.  Streamlit
remains the behavioral source of truth; the web app delegates to these helpers
instead of re-implementing buyer math in TypeScript.
"""
from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import numpy as np
import pandas as pd

from modules.buyer_assortment import build_assortment_priorities

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


def read_tabular_bytes(payload: bytes, filename: str) -> pd.DataFrame:
    if not payload:
        raise ValueError("The stored source file is empty.")
    name = str(filename or "source.csv").casefold()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(payload))
    return pd.read_csv(BytesIO(payload))


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


def _normalize_category(raw: Any) -> str:
    if pd.isna(raw) or raw is None:
        return "unknown"
    s = str(raw).lower().strip()
    if not s:
        return "unknown"
    if any(k in s for k in ["flower", "bud", "cannabis flower"]): return "flower"
    if any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint"]): return "pre rolls"
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]): return "vapes"
    if any(k in s for k in ["edible", "gummy", "gummies", "chocolate", "chew", "cookies"]): return "edibles"
    if any(k in s for k in ["beverage", "drink", "shot"]): return "beverages"
    if any(k in s for k in ["concentrate", "wax", "shatter", "crumble", "resin", "rosin", "dab", "rso"]): return "concentrates"
    if any(k in s for k in ["tincture", "drops", "sublingual"]): return "tinctures"
    if any(k in s for k in ["topical", "lotion", "cream", "salve", "balm"]): return "topicals"
    return s


def _extract_size(text: Any, context: Any = None) -> str:
    del context
    if pd.isna(text) or text is None:
        return "unspecified"
    s = str(text).lower().strip()
    mg = re.search(r"(\d+(\.\d+)?\s?mg)\b", s)
    if mg: return mg.group(1).replace(" ", "")
    grams = re.search(r"((?:\d+\.?\d*|\.\d+)\s?(g|oz))\b", s)
    if grams:
        val = grams.group(1).replace(" ", "").lower()
        return "28g" if val in ["1oz", "1.0oz", "28g", "28.0g"] else val
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]) and re.search(r"\b0\.5\b|\b\.5\b", s):
        return "0.5g"
    return "unspecified"


def _stack_parts(*parts: Any) -> str:
    clean = [str(p).strip() for p in parts if p and str(p).strip() and str(p).strip() != "unspecified"]
    return " ".join(clean) if clean else "unspecified"


def _extract_strain_type(name: Any, subcat: Any) -> str:
    s = str(name).lower().strip(); cat = str(subcat).lower().strip(); base = "unspecified"
    if "indica" in s: base = "indica"
    elif "sativa" in s: base = "sativa"
    elif "hybrid" in s: base = "hybrid"
    elif "cbd" in s: base = "cbd"
    flower_bucket = None
    if "flower" in cat:
        if "super shake" in s: flower_bucket = "super shake"
        elif "shake" in s: flower_bucket = "shake"
        elif any(k in s for k in ["small buds", "smalls", "small bud"]): flower_bucket = "small buds"
        elif "popcorn" in s: flower_bucket = "popcorn"
    vape_flag = ("vape" in cat) or any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"])
    oil = None
    if vape_flag:
        if any(k in s for k in ["liquid live resin", "live resin", "llr"]): oil = "live resin"
        elif "cured resin" in s: oil = "cured resin"
        elif "rosin" in s: oil = "rosin"
        elif any(k in s for k in ["distillate", "disty"]): oil = "distillate"
        if "disposable" in s: oil = _stack_parts(oil, "disposable")
    if "flower" in cat: return _stack_parts(base, flower_bucket)
    if vape_flag: return _stack_parts(base, oil)
    return base


def _deduplicate_inventory(inv_df: pd.DataFrame) -> pd.DataFrame:
    if inv_df is None or inv_df.empty or "batch" not in inv_df.columns:
        return inv_df
    df = inv_df.copy()
    df["batch"] = df["batch"].fillna("").astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "None": np.nan})
    has_batch = df["batch"].notna()
    if not has_batch.any(): return df
    with_batch, without_batch = df[has_batch].copy(), df[~has_batch].copy()
    agg_map: dict[str, str] = {"onhandunits": "sum"}
    for c in ["subcategory", "sku", "itemname", "unit_cost", "retail_price", "brand_vendor", "expiration_date"]:
        if c in with_batch.columns and c not in ["itemname", "batch"]:
            agg_map[c] = "min" if c == "expiration_date" else "first"
    deduped = with_batch.groupby(["itemname", "batch"], dropna=False, as_index=False).agg(agg_map)
    return pd.concat([deduped, without_batch], ignore_index=True)


def build_forecast(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, doh_threshold: int, velocity_adjustment: float, sales_period_days: int):
    inv_df = inv_raw_df.copy(); sales_raw = sales_raw_df.copy()
    inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower(); sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()
    name_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_NAME_ALIASES]); cat_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_CAT_ALIASES]); qty_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_QTY_ALIASES])
    sku_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_SKU_ALIASES]); batch_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_BATCH_ALIASES]); cost_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_COST_ALIASES]); retail_price_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES]); strain_type_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_STRAIN_TYPE_ALIASES]); brand_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_BRAND_ALIASES]); expiry_col = _detect_column(inv_df.columns, [_normalize_col(a) for a in INV_EXPIRY_ALIASES])
    if not (name_col and cat_col and qty_col): raise ValueError("Could not detect inventory product / category / on-hand columns.")
    rename_map = {name_col: "itemname", cat_col: "subcategory", qty_col: "onhandunits"}
    for source, target in [(sku_col,"sku"),(batch_col,"batch"),(strain_type_col,"_explicit_strain_type"),(retail_price_col,"retail_price"),(cost_col,"unit_cost"),(brand_col,"brand_vendor"),(expiry_col,"expiration_date")]:
        if source: rename_map[source] = target
    inv_df = inv_df.rename(columns=rename_map); inv_df["itemname"] = inv_df["itemname"].astype(str).str.strip(); inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0)
    if "unit_cost" in inv_df: inv_df["unit_cost"] = _parse_currency_to_float(inv_df["unit_cost"]).fillna(0)
    if "retail_price" in inv_df: inv_df["retail_price"] = _parse_currency_to_float(inv_df["retail_price"]).fillna(0)
    if "expiration_date" in inv_df: inv_df["expiration_date"] = pd.to_datetime(inv_df["expiration_date"], errors="coerce")
    inv_df = _deduplicate_inventory(inv_df); inv_df["subcategory"] = inv_df["subcategory"].apply(_normalize_category); inv_df["strain_type"] = inv_df.apply(lambda x: _extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")), axis=1)
    if "_explicit_strain_type" in inv_df:
        explicit = inv_df["_explicit_strain_type"].astype(str).str.strip().str.lower(); valid = explicit.isin(["indica","sativa","hybrid","cbd"]); inv_df.loc[valid,"strain_type"] = explicit[valid]; inv_df = inv_df.drop(columns=["_explicit_strain_type"])
    inv_df["packagesize"] = inv_df.apply(lambda x: _extract_size(x.get("itemname", ""), x.get("subcategory", "")), axis=1); inv_df["product_name"] = inv_df["itemname"]

    sales_name_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_NAME_ALIASES]); sales_qty_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_QTY_ALIASES]); sales_cat_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_CAT_ALIASES]); sales_rev_col = _detect_column(sales_raw.columns, [_normalize_col(a) for a in SALES_REV_ALIASES])
    if not (sales_name_col and sales_qty_col and sales_cat_col): raise ValueError("Could not detect sales product / quantity / category columns.")
    sales_raw = sales_raw.rename(columns={sales_name_col:"product_name",sales_qty_col:"unitssold",sales_cat_col:"mastercategory", **({sales_rev_col:"revenue"} if sales_rev_col else {})}); sales_raw["product_name"] = sales_raw["product_name"].astype(str).str.strip(); sales_raw["unitssold"] = pd.to_numeric(sales_raw["unitssold"], errors="coerce").fillna(0); sales_raw["mastercategory"] = sales_raw["mastercategory"].astype(str).str.strip().apply(_normalize_category)
    if "revenue" in sales_raw: sales_raw["revenue"] = _parse_currency_to_float(sales_raw["revenue"]).fillna(0)
    sales_df = sales_raw[~sales_raw["mastercategory"].astype(str).str.contains("accessor", na=False) & (sales_raw["mastercategory"] != "all")].copy(); sales_df["packagesize"] = sales_df.apply(lambda r: _extract_size(r.get("product_name", ""), r.get("mastercategory", "")), axis=1); sales_df["strain_type"] = sales_df.apply(lambda r: _extract_strain_type(r.get("product_name", ""), r.get("mastercategory", "")), axis=1)

    keys = ["subcategory","strain_type","packagesize"]
    inv_summary = inv_df.groupby(keys, dropna=False)["onhandunits"].sum().reset_index()
    for c in ["unit_cost","retail_price"]:
        if c in inv_df: inv_summary = inv_summary.merge(inv_df.groupby(keys, dropna=False)[c].median().reset_index(), on=keys, how="left")
    pkeys = ["subcategory","product_name","strain_type","packagesize"]
    inv_product = inv_df.groupby(pkeys, dropna=False)["onhandunits"].sum().reset_index()
    for c in ["brand_vendor","expiration_date","sku"]:
        if c in inv_df: inv_product = inv_product.merge(inv_df.groupby(pkeys, dropna=False)[c].first().reset_index(), on=pkeys, how="left")
    for c in ["unit_cost","retail_price"]:
        if c in inv_df: inv_product = inv_product.merge(inv_df.groupby(pkeys, dropna=False)[c].median().reset_index(), on=pkeys, how="left")
    sales_summary = sales_df.groupby(["mastercategory","packagesize"], dropna=False)["unitssold"].sum().reset_index(); sales_summary["avgunitsperday"] = (sales_summary["unitssold"] / max(int(sales_period_days),1)) * float(velocity_adjustment)
    sales_product = sales_df.groupby(["mastercategory","product_name","strain_type","packagesize"], dropna=False)["unitssold"].sum().reset_index(); sales_product["avgunitsperday"] = (sales_product["unitssold"] / max(int(sales_period_days),1)) * float(velocity_adjustment)
    detail = pd.merge(inv_summary, sales_summary, how="left", left_on=["subcategory","packagesize"], right_on=["mastercategory","packagesize"]).fillna(0); detail_product = pd.merge(inv_product, sales_product, how="left", left_on=pkeys, right_on=["mastercategory","product_name","strain_type","packagesize"]).fillna(0)
    detail["daysonhand"] = np.where(detail["avgunitsperday"] > 0, detail["onhandunits"] / detail["avgunitsperday"], 0); detail["daysonhand"] = detail["daysonhand"].replace([np.inf,-np.inf],0).fillna(0).astype(int); detail["reorderqty"] = np.where(detail["daysonhand"] < doh_threshold, np.ceil((doh_threshold-detail["daysonhand"])*detail["avgunitsperday"]), 0).astype(int)
    def tag(row):
        if row["daysonhand"] <= 7 and row["avgunitsperday"] > 0: return "1 – Reorder ASAP"
        if row["daysonhand"] <= 21 and row["avgunitsperday"] > 0: return "2 – Watch Closely"
        if row["avgunitsperday"] == 0: return "4 – Dead Item"
        return "3 – Comfortable Cover"
    detail["reorderpriority"] = detail.apply(tag, axis=1); detail_product["avgunitsperday"] = pd.to_numeric(detail_product["avgunitsperday"], errors="coerce").fillna(0); detail_product["onhandunits"] = pd.to_numeric(detail_product["onhandunits"], errors="coerce").fillna(0); detail_product["daysonhand"] = np.where(detail_product["avgunitsperday"] > 0, detail_product["onhandunits"] / detail_product["avgunitsperday"], 0); detail_product["daysonhand"] = detail_product["daysonhand"].replace([np.inf,-np.inf],0).fillna(0).astype(int)
    return detail, detail_product, inv_df, sales_df


def category_dos(detail: pd.DataFrame, detail_product: pd.DataFrame) -> pd.DataFrame:
    result = detail.groupby("subcategory", dropna=False).agg(onhandunits=("onhandunits","sum"), avgunitsperday=("avgunitsperday","sum"), reorder_lines=("reorderpriority", lambda x: int((x == "1 – Reorder ASAP").sum()))).reset_index()
    result["category_dos"] = np.where(result["avgunitsperday"] > 0, result["onhandunits"] / result["avgunitsperday"].replace(0,np.nan), 0); result["category_dos"] = result["category_dos"].replace([np.inf,-np.inf],0).fillna(0).astype(int)
    if not detail_product.empty:
        dp = detail_product[["subcategory","product_name","unitssold"]].copy(); dp["unitssold"] = pd.to_numeric(dp["unitssold"], errors="coerce").fillna(0)
        top = dp.sort_values("unitssold", ascending=False).groupby("subcategory", dropna=False, sort=False)["product_name"].apply(lambda x: ", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name":"top_products"}); count = dp.groupby("subcategory", dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name":"product_count"}); result = result.merge(top,on="subcategory",how="left").merge(count,on="subcategory",how="left"); result["product_count"] = result["product_count"].fillna(0).astype(int); result["top_products"] = result["top_products"].fillna("")
    order = {name:index for index,name in enumerate(REB_CATEGORIES)}; result["_sort"] = result["subcategory"].astype(str).str.lower().map(lambda v: order.get(v, 999)); return result.sort_values(["_sort","subcategory"]).drop(columns=["_sort"])


def forecast_view(detail: pd.DataFrame, detail_product: pd.DataFrame) -> pd.DataFrame:
    context = detail_product[["subcategory","product_name","strain_type","packagesize","unitssold"]].copy(); context["unitssold"] = pd.to_numeric(context["unitssold"], errors="coerce").fillna(0)
    top = context.sort_values("unitssold",ascending=False).groupby(["subcategory","strain_type","packagesize"],dropna=False,sort=False)["product_name"].apply(lambda x: ", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name":"top_products"}); count = detail_product.groupby(["subcategory","strain_type","packagesize"],dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name":"product_count"})
    out = detail.merge(top,on=["subcategory","strain_type","packagesize"],how="left").merge(count,on=["subcategory","strain_type","packagesize"],how="left"); out["product_count"] = out["product_count"].fillna(0).astype(int); out["top_products"] = out["top_products"].fillna(""); return out


def sku_inventory_view(detail_product: pd.DataFrame) -> pd.DataFrame:
    view = detail_product.copy()
    if "unit_cost" in view: view["dollars_on_hand"] = view["onhandunits"] * pd.to_numeric(view["unit_cost"], errors="coerce").fillna(0)
    if "retail_price" in view: view["retail_dollars_on_hand"] = view["onhandunits"] * pd.to_numeric(view["retail_price"], errors="coerce").fillna(0)
    if "expiration_date" in view:
        today = pd.Timestamp.today().normalize(); view["expiration_date"] = pd.to_datetime(view["expiration_date"], errors="coerce"); view["days_to_expire"] = (view["expiration_date"]-today).dt.days
    view["days_of_supply"] = np.where(pd.to_numeric(view["avgunitsperday"], errors="coerce").fillna(0)>0, pd.to_numeric(view["onhandunits"], errors="coerce").fillna(0)/pd.to_numeric(view["avgunitsperday"], errors="coerce").replace(0,np.nan), UNKNOWN_DAYS_OF_SUPPLY); view["weeks_of_supply"] = (view["days_of_supply"]/7).round(1)
    def status(row):
        if row["onhandunits"] <= 0: return "⬛ No Stock"
        if "days_to_expire" in row.index and pd.notna(row.get("days_to_expire")) and row.get("days_to_expire") < INVENTORY_EXPIRING_SOON_DAYS: return "⚠️ Expiring"
        if 0 < row["days_of_supply"] <= INVENTORY_REORDER_DOH_THRESHOLD: return "🔴 Reorder"
        if row["days_of_supply"] >= INVENTORY_OVERSTOCK_DOH_THRESHOLD: return "🟠 Overstock"
        return "✅ Healthy"
    view["status"] = view.apply(status, axis=1); return view


def trends(detail_product: pd.DataFrame, sales_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    category = sales_df.groupby("mastercategory", dropna=False).agg(units=("unitssold","sum"), revenue=("revenue","sum") if "revenue" in sales_df else ("unitssold","sum")).reset_index().rename(columns={"mastercategory":"category"}).sort_values("units",ascending=False)
    package = sales_df.groupby(["mastercategory","packagesize"], dropna=False)["unitssold"].sum().reset_index().rename(columns={"mastercategory":"category","unitssold":"units"}).sort_values("units",ascending=False)
    top = sales_df.groupby("product_name", dropna=False).agg(units=("unitssold","sum"), revenue=("revenue","sum") if "revenue" in sales_df else ("unitssold","sum")).reset_index().sort_values("units",ascending=False)
    sellers = sales_df.groupby(["mastercategory","product_name"],dropna=False)["unitssold"].sum().reset_index().rename(columns={"mastercategory":"category","unitssold":"units"}).sort_values(["category","units"],ascending=[True,False]); sellers = sellers.groupby("category",sort=False).head(5).reset_index(drop=True)
    fast = detail_product.copy(); fast["avgunitsperday"] = pd.to_numeric(fast["avgunitsperday"], errors="coerce").fillna(0); fast["daysonhand"] = pd.to_numeric(fast["daysonhand"], errors="coerce").fillna(0); fast = fast[(fast["avgunitsperday"]>0)&(fast["daysonhand"]<=INVENTORY_REORDER_DOH_THRESHOLD)].sort_values(["avgunitsperday","daysonhand"],ascending=[False,True])
    return {"category_mix":category,"package_size_mix":package,"top_movers":top,"best_sellers_by_category":sellers,"fast_movers_low_stock":fast}


def buyer_intelligence(detail_product: pd.DataFrame) -> dict[str, Any]:
    frame = detail_product.rename(columns={"subcategory":"category","packagesize":"package_size","avgunitsperday":"avg_daily_units","onhandunits":"on_hand_units","unitssold":"units_sold","daysonhand":"days_of_cover"}).copy()
    required = ["product_name","category","strain_type","package_size","avg_daily_units","on_hand_units","units_sold","days_of_cover"]
    for column in required:
        if column not in frame: frame[column] = 0 if column in {"avg_daily_units","on_hand_units","units_sold","days_of_cover"} else ""
    priorities = build_assortment_priorities(frame[required]); numeric_cover = pd.to_numeric(frame["days_of_cover"],errors="coerce"); sold = pd.to_numeric(frame["units_sold"],errors="coerce").fillna(0); onhand = pd.to_numeric(frame["on_hand_units"],errors="coerce").fillna(0)
    risk = frame[(numeric_cover<=14)&(pd.to_numeric(frame["avg_daily_units"],errors="coerce").fillna(0)>0)].sort_values(["days_of_cover","units_sold"],ascending=[True,False]).head(50); overstock = frame[(onhand>0)&((sold<=0)|(numeric_cover>=60))].sort_values(["units_sold","days_of_cover"],ascending=[True,False]).head(50)
    category_risk = frame.assign(at_risk=((numeric_cover<=14)&(pd.to_numeric(frame["avg_daily_units"],errors="coerce").fillna(0)>0)), overstock=((onhand>0)&((sold<=0)|(numeric_cover>=60)))).groupby("category",dropna=False).agg(skus=("product_name","nunique"),units_sold=("units_sold","sum"),on_hand=("on_hand_units","sum"),at_risk=("at_risk","sum"),overstock=("overstock","sum")).reset_index()
    return {"summary":{"tracked_skus":int(frame["product_name"].nunique()),"total_units_sold":float(sold.sum()),"at_risk_skus":int(len(risk)),"overstock_watch":int(len(overstock))},"purchase_priorities":priorities,"sku_risk":risk,"overstock_watch":overstock,"category_risk":category_risk}


def xlsx_bytes(frame: pd.DataFrame, sheet_name: str = "Forecast") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer: frame.to_excel(writer,index=False,sheet_name=sheet_name[:31])
    return output.getvalue()


def records(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    if frame is None or frame.empty: return []
    clean = frame.head(limit).copy() if limit else frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]): clean[column] = clean[column].dt.strftime("%Y-%m-%d")
    clean = clean.replace([np.inf,-np.inf],np.nan).where(pd.notna(clean), None)
    return clean.to_dict("records")
