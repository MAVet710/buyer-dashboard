"""UI-independent Buyer Dash parity calculations used by React/FastAPI.

The formulas, aliases, category/strain classifiers, synthetic size rows and SKU
velocity logic in this module are ported from ``views/buyer_perfect_view.py``.
Streamlit remains the behavioral source of truth; this module removes only the
Streamlit presentation dependency.
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
VALID_STRAIN_TYPES = frozenset(["indica", "sativa", "hybrid", "cbd", "indica dominant hybrid", "sativa dominant hybrid"])
REB_CATEGORIES = ["flower", "pre rolls", "vapes", "edibles", "beverages", "concentrates", "tinctures", "topicals"]

INV_NAME_ALIASES = ["product", "productname", "item", "itemname", "name", "skuname", "skuid", "product name", "product_name", "product title", "title"]
INV_CAT_ALIASES = ["category", "subcategory", "productcategory", "department", "mastercategory", "product category", "cannabis", "product_category", "ecomm category", "ecommcategory"]
INV_QTY_ALIASES = ["available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand", "instock", "currentquantity", "current quantity", "inventoryavailable", "inventory available", "available quantity", "med total", "medtotal", "med sellable", "medsellable"]
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


def read_tabular_bytes(payload: bytes, filename: str) -> pd.DataFrame:
    if not payload: raise ValueError("The stored source file is empty.")
    name = str(filename or "source.csv").casefold()
    return pd.read_excel(BytesIO(payload)) if name.endswith((".xlsx", ".xls")) else pd.read_csv(BytesIO(payload))


def _normalize_col(col: str) -> str: return re.sub(r"[^a-z0-9]", "", str(col).lower())
def _detect_column(columns, aliases):
    norm_map = {_normalize_col(c): c for c in columns}
    for alias in aliases:
        key = _normalize_col(alias)
        if key in norm_map: return norm_map[key]
    return None


def _parse_currency_to_float(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"^\$", "", regex=True).str.replace(",", "", regex=False).pipe(lambda s: pd.to_numeric(s, errors="coerce"))


def _normalize_category(raw: Any) -> str:
    if pd.isna(raw) or raw is None: return "unknown"
    s = str(raw).lower().strip()
    if not s: return "unknown"
    if any(k in s for k in ["flower", "bud", "buds", "cannabis flower"]): return "flower"
    if any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint", "joints"]): return "pre rolls"
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]): return "vapes"
    if any(k in s for k in ["edible", "gummy", "gummies", "chocolate", "chew", "cookies"]): return "edibles"
    if any(k in s for k in ["beverage", "drink", "drinkable", "shot", "beverages"]): return "beverages"
    if any(k in s for k in ["concentrate", "wax", "shatter", "crumble", "resin", "rosin", "dab", "rso"]): return "concentrates"
    if any(k in s for k in ["tincture", "tinctures", "drops", "sublingual", "dropper"]): return "tinctures"
    if any(k in s for k in ["topical", "lotion", "cream", "salve", "balm"]): return "topicals"
    return s


def _extract_size(text: Any, context: Any = None) -> str:
    del context
    if pd.isna(text) or text is None: return "unspecified"
    s = str(text).lower().strip()
    if not s: return "unspecified"
    mg = re.search(r"(\d+(\.\d+)?\s?mg)\b", s)
    if mg: return mg.group(1).replace(" ", "")
    grams = re.search(r"((?:\d+\.?\d*|\.\d+)\s?(g|oz))\b", s)
    if grams:
        value = grams.group(1).replace(" ", "").lower()
        return "28g" if value in ["1oz", "1.0oz", "28g", "28.0g"] else value
    if any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"]) and re.search(r"\b0\.5\b|\b\.5\b", s): return "0.5g"
    return "unspecified"


def _stack_parts(*parts: Any) -> str:
    clean = [str(part).strip() for part in parts if part and str(part).strip() and str(part).strip() != "unspecified"]
    return " ".join(clean) if clean else "unspecified"


def _extract_strain_type(name: Any, subcat: Any) -> str:
    s = "" if pd.isna(name) else str(name).lower().strip(); cat = "" if pd.isna(subcat) else str(subcat).lower().strip()
    base = "unspecified"
    if "indica" in s: base = "indica"
    elif "sativa" in s: base = "sativa"
    elif "hybrid" in s: base = "hybrid"
    elif "cbd" in s: base = "cbd"
    rr_tag = None
    if "flower" in cat:
        if re.search(r"\brise\b", s): rr_tag = "rise"; base = "sativa" if base == "unspecified" else base
        elif re.search(r"\brefresh\b", s): rr_tag = "refresh"; base = "hybrid" if base == "unspecified" else base
        elif re.search(r"\brest\b", s): rr_tag = "rest"; base = "indica" if base == "unspecified" else base
    vape_flag = ("vape" in cat) or any(k in s for k in ["vape", "cart", "cartridge", "pen", "pod"])
    preroll_flag = ("pre roll" in cat) or ("pre rolls" in cat) or any(k in s for k in ["pre roll", "preroll", "pre-roll", "joint"])
    flower_bucket = None
    if "flower" in cat:
        if "super shake" in s: flower_bucket = "super shake"
        elif re.search(r"\bshake\b", s): flower_bucket = "shake"
        elif any(k in s for k in ["small buds", "smalls", "small bud"]): flower_bucket = "small buds"
        elif "popcorn" in s: flower_bucket = "popcorn"
    oil = None
    if vape_flag:
        if any(k in s for k in ["liquid live resin", "live resin", "llr"]): oil = "live resin"
        elif "cured resin" in s: oil = "cured resin"
        elif "rosin" in s: oil = "rosin"
        elif any(k in s for k in ["distillate", "disty"]): oil = "distillate"
    if vape_flag and (("disposable" in s) or ("dispos" in s)): oil = _stack_parts(oil, "disposable")
    infused = "infused" if preroll_flag and "infused" in s else None
    edible_form = None
    if "edible" in cat:
        if any(k in s for k in ["gummy", "gummies", "chew", "fruit chew"]): edible_form = "gummy"
        elif any(k in s for k in ["chocolate", "choc"]): edible_form = "chocolate"
    conc_tag = "rso" if "concentrate" in cat and ("rso" in s or "rick simpson" in s) else None
    if "flower" in cat: return _stack_parts(base, flower_bucket, rr_tag)
    if vape_flag: return _stack_parts(base, oil)
    if "edible" in cat: return _stack_parts(base, edible_form)
    if "concentrate" in cat: return _stack_parts(base, conc_tag)
    if preroll_flag: return _stack_parts(base, infused)
    return base


def _deduplicate_inventory(inv_df: pd.DataFrame) -> pd.DataFrame:
    if inv_df is None or inv_df.empty or "batch" not in inv_df.columns: return inv_df
    df = inv_df.copy(); df["batch"] = df["batch"].fillna("").astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "NaN": np.nan, "NAN": np.nan, "none": np.nan, "None": np.nan, "NONE": np.nan, "<NA>": np.nan})
    has_batch = df["batch"].notna()
    if not has_batch.any(): return df
    with_batch, without_batch = df[has_batch].copy(), df[~has_batch].copy(); agg_map: dict[str, str] = {"onhandunits": "sum"}
    for c in ["subcategory", "sku", "unit_cost", "retail_price", "brand_vendor", "expiration_date"]:
        if c in with_batch.columns and c not in ["itemname", "batch"]: agg_map[c] = "first" if c != "expiration_date" else "min"
    deduped = with_batch.groupby(["itemname", "batch"], dropna=False, as_index=False).agg(agg_map)
    return pd.concat([deduped, without_batch], ignore_index=True)


def _parse_grams_from_size(value: Any) -> float | None:
    s = str(value).lower().strip()
    if s in {"28g", "1oz", "1.0oz"}: return 28.0
    match = re.match(r"^(\d+(\.\d+)?)g$", s)
    if match: return float(match.group(1))
    match = re.match(r"^(\d+(\.\d+)?)oz$", s)
    return float(match.group(1)) * 28.0 if match else None


def _parse_mg_from_size(value: Any) -> float | None:
    match = re.match(r"^(\d+(\.\d+)?)mg$", str(value).lower().strip())
    return float(match.group(1)) if match else None


def build_forecast(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, doh_threshold: int, velocity_adjustment: float, sales_period_days: int):
    inv_df = inv_raw_df.copy(); sales_raw = sales_raw_df.copy(); inv_df.columns = inv_df.columns.astype(str).str.strip().str.lower(); sales_raw.columns = sales_raw.columns.astype(str).str.strip().str.lower()
    name_col = _detect_column(inv_df.columns, INV_NAME_ALIASES); cat_col = _detect_column(inv_df.columns, INV_CAT_ALIASES); qty_col = _detect_column(inv_df.columns, INV_QTY_ALIASES); sku_col = _detect_column(inv_df.columns, INV_SKU_ALIASES); batch_col = _detect_column(inv_df.columns, INV_BATCH_ALIASES); cost_col = _detect_column(inv_df.columns, INV_COST_ALIASES); retail_price_col = _detect_column(inv_df.columns, INV_RETAIL_PRICE_ALIASES); strain_type_col = _detect_column(inv_df.columns, INV_STRAIN_TYPE_ALIASES); brand_col = _detect_column(inv_df.columns, INV_BRAND_ALIASES); expiry_col = _detect_column(inv_df.columns, INV_EXPIRY_ALIASES)
    if not (name_col and cat_col and qty_col): raise ValueError("Could not auto-detect inventory columns (product / category / on-hand).")
    inv_df = inv_df.rename(columns={name_col:"itemname",cat_col:"subcategory",qty_col:"onhandunits"})
    for source,target in [(sku_col,"sku"),(batch_col,"batch"),(strain_type_col,"_explicit_strain_type"),(retail_price_col,"retail_price"),(cost_col,"unit_cost"),(brand_col,"brand_vendor"),(expiry_col,"expiration_date")]:
        if source: inv_df = inv_df.rename(columns={source:target})
    if "retail_price" in inv_df: inv_df["retail_price"] = _parse_currency_to_float(inv_df["retail_price"])
    if "unit_cost" in inv_df: inv_df["unit_cost"] = _parse_currency_to_float(inv_df["unit_cost"]).fillna(0)
    if "expiration_date" in inv_df: inv_df["expiration_date"] = pd.to_datetime(inv_df["expiration_date"], errors="coerce")
    inv_df["itemname"] = inv_df["itemname"].astype(str).str.strip(); inv_df["onhandunits"] = pd.to_numeric(inv_df["onhandunits"], errors="coerce").fillna(0); inv_df = _deduplicate_inventory(inv_df); inv_df["subcategory"] = inv_df["subcategory"].apply(_normalize_category); inv_df["strain_type"] = inv_df.apply(lambda x:_extract_strain_type(x.get("itemname",""),x.get("subcategory","")),axis=1)
    if "_explicit_strain_type" in inv_df:
        explicit = inv_df["_explicit_strain_type"].astype(str).str.strip().str.lower(); valid = explicit.isin(VALID_STRAIN_TYPES); inv_df.loc[valid,"strain_type"] = explicit[valid]; inv_df = inv_df.drop(columns=["_explicit_strain_type"])
    inv_df["packagesize"] = inv_df.apply(lambda x:_extract_size(x.get("itemname",""),x.get("subcategory","")),axis=1); inv_df["product_name"] = inv_df["itemname"]

    keys=["subcategory","strain_type","packagesize"]; inv_summary=inv_df.groupby(keys,dropna=False)["onhandunits"].sum().reset_index()
    for c in ["unit_cost","retail_price"]:
        if c in inv_df: inv_summary=inv_summary.merge(inv_df.groupby(keys,dropna=False)[c].median().reset_index(),on=keys,how="left")
    pkeys=["subcategory","product_name","strain_type","packagesize"]; inv_product=inv_df.groupby(pkeys,dropna=False)["onhandunits"].sum().reset_index()
    for c in ["brand_vendor","sku","expiration_date","unit_cost","retail_price"]:
        if c in inv_df: inv_product=inv_product.merge(inv_df.groupby(pkeys,dropna=False)[c].first().reset_index(),on=pkeys,how="left")

    sales_name=_detect_column(sales_raw.columns,SALES_NAME_ALIASES); sales_qty=_detect_column(sales_raw.columns,SALES_QTY_ALIASES); sales_cat=_detect_column(sales_raw.columns,SALES_CAT_ALIASES); sales_sku=_detect_column(sales_raw.columns,SALES_SKU_ALIASES); sales_rev=_detect_column(sales_raw.columns,SALES_REV_ALIASES)
    if not (sales_name and sales_qty and sales_cat): raise ValueError("Could not detect required sales columns (name, quantity, category).")
    sales_raw=sales_raw.rename(columns={sales_name:"product_name",sales_qty:"unitssold",sales_cat:"mastercategory"})
    if sales_sku: sales_raw=sales_raw.rename(columns={sales_sku:"sku"})
    if sales_rev: sales_raw=sales_raw.rename(columns={sales_rev:"net_sales"})
    sales_raw["product_name"]=sales_raw["product_name"].astype(str).str.strip(); sales_raw["unitssold"]=pd.to_numeric(sales_raw["unitssold"],errors="coerce").fillna(0)
    if "net_sales" in sales_raw: sales_raw["net_sales"]=pd.to_numeric(sales_raw["net_sales"],errors="coerce").fillna(0)
    sales_raw["mastercategory"]=sales_raw["mastercategory"].astype(str).str.strip().apply(_normalize_category); sales_df=sales_raw[~sales_raw["mastercategory"].astype(str).str.contains("accessor",na=False)&(sales_raw["mastercategory"]!="all")].copy(); sales_df["packagesize"]=sales_df.apply(lambda row:_extract_size(row.get("product_name",""),row.get("mastercategory","")),axis=1); sales_df["strain_type"]=sales_df.apply(lambda row:_extract_strain_type(row.get("product_name",""),row.get("mastercategory","")),axis=1); sales_detail_df=sales_df.drop_duplicates().copy()
    sales_summary=sales_df.groupby(["mastercategory","packagesize"],dropna=False)["unitssold"].sum().reset_index(); sales_summary["avgunitsperday"]=(sales_summary["unitssold"]/max(int(sales_period_days),1))*float(velocity_adjustment)
    sales_product=sales_df.groupby(["mastercategory","product_name","strain_type","packagesize"],dropna=False)["unitssold"].sum().reset_index(); sales_product["avgunitsperday"]=(sales_product["unitssold"]/max(int(sales_period_days),1))*float(velocity_adjustment)
    detail_product=pd.merge(inv_product,sales_product,how="left",left_on=pkeys,right_on=["mastercategory","product_name","strain_type","packagesize"]).fillna(0); detail=pd.merge(inv_summary,sales_summary,how="left",left_on=["subcategory","packagesize"],right_on=["mastercategory","packagesize"]).fillna(0)

    flower_cats=detail.loc[detail["subcategory"].astype(str).str.contains("flower",na=False),"subcategory"].unique().tolist(); missing=[]
    def estimate_28(cat):
        direct=sales_df[(sales_df["mastercategory"]==cat)&(sales_df["packagesize"]=="28g")]
        if not direct.empty:
            units=float(direct["unitssold"].sum()); return units,(units/max(int(sales_period_days),1))*float(velocity_adjustment)
        cat_sales=sales_df[sales_df["mastercategory"]==cat]; total=sum(float(r.get("unitssold",0))*grams for _,r in cat_sales.iterrows() if (grams:=_parse_grams_from_size(r.get("packagesize","unspecified"))) is not None)
        units=total/28.0 if total>0 else 0.0; return units,(units/max(int(sales_period_days),1))*float(velocity_adjustment)
    for cat in flower_cats:
        mask=(detail["subcategory"]==cat)&(detail["packagesize"]=="28g")
        if not mask.any():
            units,avg=estimate_28(cat); missing.append({"subcategory":cat,"strain_type":"unspecified","packagesize":"28g","onhandunits":0,"mastercategory":cat,"unitssold":units,"avgunitsperday":avg})
        elif float(detail.loc[mask,"avgunitsperday"].iloc[0])==0:
            units,avg=estimate_28(cat)
            if avg>0: detail.loc[mask,"unitssold"]=units; detail.loc[mask,"avgunitsperday"]=avg
    if missing: detail=pd.concat([detail,pd.DataFrame(missing)],ignore_index=True)

    edible_cats=detail.loc[detail["subcategory"].astype(str).str.contains("edible",na=False),"subcategory"].unique().tolist(); missing=[]
    def estimate_500(cat):
        direct=sales_df[(sales_df["mastercategory"]==cat)&(sales_df["packagesize"]=="500mg")]
        if not direct.empty:
            units=float(direct["unitssold"].sum()); return units,(units/max(int(sales_period_days),1))*float(velocity_adjustment)
        cat_sales=sales_df[sales_df["mastercategory"]==cat]; total=sum(float(r.get("unitssold",0))*mg for _,r in cat_sales.iterrows() if (mg:=_parse_mg_from_size(r.get("packagesize","unspecified"))) is not None)
        units=total/500.0 if total>0 else 0.0; return units,(units/max(int(sales_period_days),1))*float(velocity_adjustment)
    for cat in edible_cats:
        mask=(detail["subcategory"]==cat)&(detail["packagesize"]=="500mg")
        if not mask.any():
            units,avg=estimate_500(cat); missing.append({"subcategory":cat,"strain_type":"unspecified","packagesize":"500mg","onhandunits":0,"mastercategory":cat,"unitssold":units,"avgunitsperday":avg})
        elif float(detail.loc[mask,"avgunitsperday"].iloc[0])==0:
            units,avg=estimate_500(cat)
            if avg>0: detail.loc[mask,"unitssold"]=units; detail.loc[mask,"avgunitsperday"]=avg
    if missing: detail=pd.concat([detail,pd.DataFrame(missing)],ignore_index=True)

    detail["daysonhand"]=np.where(detail["avgunitsperday"]>0,detail["onhandunits"]/detail["avgunitsperday"],0); detail["daysonhand"]=detail["daysonhand"].replace([np.inf,-np.inf],0).fillna(0).astype(int); detail["reorderqty"]=np.where(detail["daysonhand"]<doh_threshold,np.ceil((doh_threshold-detail["daysonhand"])*detail["avgunitsperday"]),0).astype(int)
    def tag(row):
        if row["daysonhand"]<=7 and row["avgunitsperday"]>0:return "1 – Reorder ASAP"
        if row["daysonhand"]<=21 and row["avgunitsperday"]>0:return "2 – Watch Closely"
        if row["avgunitsperday"]==0:return "4 – Dead Item"
        return "3 – Comfortable Cover"
    detail["reorderpriority"]=detail.apply(tag,axis=1); detail_product["avgunitsperday"]=pd.to_numeric(detail_product["avgunitsperday"],errors="coerce").fillna(0); detail_product["onhandunits"]=pd.to_numeric(detail_product["onhandunits"],errors="coerce").fillna(0); detail_product["daysonhand"]=np.where(detail_product["avgunitsperday"]>0,detail_product["onhandunits"]/detail_product["avgunitsperday"],0); detail_product["daysonhand"]=detail_product["daysonhand"].replace([np.inf,-np.inf],0).fillna(0).astype(int)
    return detail,detail_product,inv_df,sales_detail_df


def category_dos(detail: pd.DataFrame, detail_product: pd.DataFrame) -> pd.DataFrame:
    result=detail.groupby("subcategory",dropna=False).agg(onhandunits=("onhandunits","sum"),avgunitsperday=("avgunitsperday","sum"),reorder_lines=("reorderpriority",lambda x:int((x=="1 – Reorder ASAP").sum()))).reset_index(); result["category_dos"]=np.where(result["avgunitsperday"]>0,result["onhandunits"]/result["avgunitsperday"],0); result["category_dos"]=result["category_dos"].replace([np.inf,-np.inf],0).fillna(0).astype(int)
    dp=detail_product[["subcategory","product_name","unitssold"]].copy(); dp["unitssold"]=pd.to_numeric(dp["unitssold"],errors="coerce").fillna(0); top=dp.sort_values("unitssold",ascending=False).groupby("subcategory",dropna=False,sort=False)["product_name"].apply(lambda x:", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name":"top_products"}); count=dp.groupby("subcategory",dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name":"product_count"}); result=result.merge(top,on="subcategory",how="left").merge(count,on="subcategory",how="left"); result["product_count"]=result["product_count"].fillna(0).astype(int); result["top_products"]=result["top_products"].fillna(""); order={name:index for index,name in enumerate(REB_CATEGORIES)}; result["_sort"]=result["subcategory"].astype(str).str.lower().map(lambda value:order.get(value,999)); return result.sort_values(["_sort","subcategory"]).drop(columns=["_sort"])


def forecast_view(detail: pd.DataFrame, detail_product: pd.DataFrame) -> pd.DataFrame:
    context=detail_product[["subcategory","product_name","strain_type","packagesize","unitssold"]].copy(); context["unitssold"]=pd.to_numeric(context["unitssold"],errors="coerce").fillna(0); top=context.sort_values("unitssold",ascending=False).groupby(["subcategory","strain_type","packagesize"],dropna=False,sort=False)["product_name"].apply(lambda x:", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name":"top_products"}); count=detail_product.groupby(["subcategory","strain_type","packagesize"],dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name":"product_count"}); out=detail.merge(top,on=["subcategory","strain_type","packagesize"],how="left").merge(count,on=["subcategory","strain_type","packagesize"],how="left"); out["product_count"]=out["product_count"].fillna(0).astype(int); out["top_products"]=out["top_products"].fillna(""); return out


def sku_inventory_view(inv_df: pd.DataFrame, sales_detail_df: pd.DataFrame, vel_window: int) -> pd.DataFrame:
    inv_roll=inv_df.copy(); agg_map={"onhandunits":"sum"}
    for c in ["unit_cost","retail_price","brand_vendor","subcategory","sku","expiration_date"]:
        if c in inv_roll.columns: agg_map[c]="first" if c!="expiration_date" else "min"
    sku_df=inv_roll.groupby("product_name",dropna=False).agg(agg_map).reset_index().rename(columns={"subcategory":"category"}); sales=sales_detail_df.copy(); date_cols=[c for c in sales.columns if "date" in c]
    if date_cols:
        date_col=date_cols[0]; sales[date_col]=pd.to_datetime(sales[date_col],errors="coerce"); max_date=sales[date_col].max()
        if pd.notna(max_date): sales=sales[sales[date_col]>=(max_date-pd.Timedelta(days=vel_window))].copy()
    vel=sales.groupby("product_name")["unitssold"].sum().reset_index().rename(columns={"unitssold":"total_sold"}); vel["daily_run_rate"]=vel["total_sold"]/max(vel_window,1); vel["avg_weekly_sales"]=vel["daily_run_rate"]*7; sku_df=sku_df.merge(vel,on="product_name",how="left")
    for c in ["total_sold","daily_run_rate","avg_weekly_sales"]: sku_df[c]=sku_df[c].fillna(0)
    sku_df["days_of_supply"]=np.where(sku_df["daily_run_rate"]>0,sku_df["onhandunits"]/sku_df["daily_run_rate"],UNKNOWN_DAYS_OF_SUPPLY); sku_df["weeks_of_supply"]=(sku_df["days_of_supply"]/7).round(1)
    if "unit_cost" in sku_df: sku_df["dollars_on_hand"]=sku_df["onhandunits"]*pd.to_numeric(sku_df["unit_cost"],errors="coerce").fillna(0)
    if "retail_price" in sku_df: sku_df["retail_dollars_on_hand"]=sku_df["onhandunits"]*pd.to_numeric(sku_df["retail_price"],errors="coerce").fillna(0)
    if "expiration_date" in sku_df: sku_df["days_to_expire"]=(pd.to_datetime(sku_df["expiration_date"],errors="coerce")-pd.Timestamp.today().normalize()).dt.days
    def status(row):
        if row["onhandunits"]<=0:return "⬛ No Stock"
        if "days_to_expire" in row.index and pd.notna(row.get("days_to_expire")) and row.get("days_to_expire")<INVENTORY_EXPIRING_SOON_DAYS:return "⚠️ Expiring"
        if 0<row["days_of_supply"]<=INVENTORY_REORDER_DOH_THRESHOLD:return "🔴 Reorder"
        if row["days_of_supply"]>=INVENTORY_OVERSTOCK_DOH_THRESHOLD:return "🟠 Overstock"
        return "✅ Healthy"
    sku_df["status"]=sku_df.apply(status,axis=1); return sku_df


def trends(detail_product: pd.DataFrame, sales_df: pd.DataFrame) -> dict[str,pd.DataFrame]:
    revenue_col="net_sales" if "net_sales" in sales_df.columns else None
    category=sales_df.groupby("mastercategory",dropna=False).agg(units=("unitssold","sum"),revenue=(revenue_col,"sum") if revenue_col else ("unitssold","sum")).reset_index().rename(columns={"mastercategory":"category"}).sort_values("units",ascending=False)
    package=sales_df.groupby(["mastercategory","packagesize"],dropna=False)["unitssold"].sum().reset_index().rename(columns={"mastercategory":"category","unitssold":"units"}).sort_values("units",ascending=False)
    top=sales_df.groupby("product_name",dropna=False).agg(units=("unitssold","sum"),revenue=(revenue_col,"sum") if revenue_col else ("unitssold","sum")).reset_index().sort_values("units",ascending=False)
    sellers=sales_df.groupby(["mastercategory","product_name"],dropna=False)["unitssold"].sum().reset_index().rename(columns={"mastercategory":"category","unitssold":"units"}).sort_values(["category","units"],ascending=[True,False]); sellers=sellers.groupby("category",sort=False).head(5).reset_index(drop=True)
    fast=detail_product.copy(); fast["avgunitsperday"]=pd.to_numeric(fast["avgunitsperday"],errors="coerce").fillna(0); fast["daysonhand"]=pd.to_numeric(fast["daysonhand"],errors="coerce").fillna(0); fast=fast[(fast["avgunitsperday"]>0)&(fast["daysonhand"]<=INVENTORY_REORDER_DOH_THRESHOLD)].sort_values(["avgunitsperday","daysonhand"],ascending=[False,True])
    return {"category_mix":category,"package_size_mix":package,"top_movers":top,"best_sellers_by_category":sellers,"fast_movers_low_stock":fast}


def buyer_intelligence(detail_product: pd.DataFrame) -> dict[str,Any]:
    frame=detail_product.rename(columns={"subcategory":"category","packagesize":"package_size","avgunitsperday":"avg_daily_units","onhandunits":"on_hand_units","unitssold":"units_sold","daysonhand":"days_of_cover"}).copy(); required=["product_name","category","strain_type","package_size","avg_daily_units","on_hand_units","units_sold","days_of_cover"]
    for column in required:
        if column not in frame: frame[column]=0 if column in {"avg_daily_units","on_hand_units","units_sold","days_of_cover"} else ""
    priorities=build_assortment_priorities(frame[required]); numeric_cover=pd.to_numeric(frame["days_of_cover"],errors="coerce"); sold=pd.to_numeric(frame["units_sold"],errors="coerce").fillna(0); onhand=pd.to_numeric(frame["on_hand_units"],errors="coerce").fillna(0); velocity=pd.to_numeric(frame["avg_daily_units"],errors="coerce").fillna(0); risk=frame[(numeric_cover<=14)&(velocity>0)].sort_values(["days_of_cover","units_sold"],ascending=[True,False]).head(50); overstock=frame[(onhand>0)&((sold<=0)|(numeric_cover>=60))].sort_values(["units_sold","days_of_cover"],ascending=[True,False]).head(50); category_risk=frame.assign(at_risk=((numeric_cover<=14)&(velocity>0)),overstock=((onhand>0)&((sold<=0)|(numeric_cover>=60)))).groupby("category",dropna=False).agg(skus=("product_name","nunique"),units_sold=("units_sold","sum"),on_hand=("on_hand_units","sum"),at_risk=("at_risk","sum"),overstock=("overstock","sum")).reset_index(); return {"summary":{"tracked_skus":int(frame["product_name"].nunique()),"total_units_sold":float(sold.sum()),"at_risk_skus":int(len(risk)),"overstock_watch":int(len(overstock))},"purchase_priorities":priorities,"sku_risk":risk,"overstock_watch":overstock,"category_risk":category_risk}


def xlsx_bytes(frame:pd.DataFrame,sheet_name:str="Forecast")->bytes:
    output=BytesIO()
    with pd.ExcelWriter(output,engine="openpyxl") as writer: frame.to_excel(writer,index=False,sheet_name=sheet_name[:31])
    return output.getvalue()


def records(frame:pd.DataFrame,*,limit:int|None=None)->list[dict[str,Any]]:
    if frame is None or frame.empty:return []
    clean=frame.head(limit).copy() if limit else frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):clean[column]=clean[column].dt.strftime("%Y-%m-%d")
    clean=clean.replace([np.inf,-np.inf],np.nan).where(pd.notna(clean),None); return clean.to_dict("records")
