"""Exact business-rule port of views/slow_movers_view.py for the web app."""
from __future__ import annotations

from io import BytesIO
import re

import numpy as np
import pandas as pd

UNKNOWN_DOH = 999


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _detect(columns, aliases):
    cmap = {_norm(column): column for column in columns}
    for alias in aliases:
        if alias in cmap:
            return cmap[alias]
    return None


def _currency_to_float(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"^\$", "", regex=True)
        .str.replace(",", "", regex=False)
        .pipe(lambda values: pd.to_numeric(values, errors="coerce"))
    )


def _normalize_category(raw):
    if pd.isna(raw):
        return "unknown"
    value = str(raw).strip().lower()
    if any(key in value for key in ["flower", "bud"]): return "flower"
    if any(key in value for key in ["pre roll", "preroll", "joint"]): return "pre rolls"
    if any(key in value for key in ["vape", "cart", "cartridge", "pen", "pod"]): return "vapes"
    if any(key in value for key in ["edible", "gummy", "chocolate", "chew"]): return "edibles"
    if any(key in value for key in ["beverage", "drink", "shot"]): return "beverages"
    if any(key in value for key in ["concentrate", "wax", "shatter", "resin", "rosin", "dab"]): return "concentrates"
    if any(key in value for key in ["tincture", "drops"]): return "tinctures"
    if any(key in value for key in ["topical", "cream", "salve", "balm"]): return "topicals"
    return value or "unknown"


def build_slow_movers(inv_raw_df: pd.DataFrame, sales_raw_df: pd.DataFrame, velocity_days: int) -> pd.DataFrame:
    inv = inv_raw_df.copy(); sales = sales_raw_df.copy()
    inv.columns = inv.columns.astype(str).str.strip().str.lower(); sales.columns = sales.columns.astype(str).str.strip().str.lower()
    inv_name = _detect(inv.columns, ["product", "productname", "item", "itemname", "name", "productname"])
    inv_cat = _detect(inv.columns, ["category", "subcategory", "productcategory", "department", "mastercategory"])
    inv_qty = _detect(inv.columns, ["available", "onhand", "onhandunits", "quantity", "qty", "quantityonhand", "instock"])
    inv_brand = _detect(inv.columns, ["brand", "brandname", "vendor", "vendorname", "manufacturer", "producer"])
    inv_cost = _detect(inv.columns, ["cost", "unitcost", "cogs", "wholesaleprice", "wholesale"])
    inv_retail = _detect(inv.columns, ["retail", "retailprice", "medprice", "msrp"])
    if not (inv_name and inv_cat and inv_qty): raise ValueError("Could not detect inventory product/category/on-hand columns.")
    inv = inv.rename(columns={inv_name:"product_name",inv_cat:"category",inv_qty:"onhandunits"})
    if inv_brand: inv = inv.rename(columns={inv_brand:"brand"})
    if inv_cost: inv = inv.rename(columns={inv_cost:"unit_cost"})
    if inv_retail: inv = inv.rename(columns={inv_retail:"retail_price"})
    inv["product_name"] = inv["product_name"].astype(str).str.strip(); inv["category"] = inv["category"].apply(_normalize_category); inv["onhandunits"] = pd.to_numeric(inv["onhandunits"], errors="coerce").fillna(0)
    if "unit_cost" in inv: inv["unit_cost"] = _currency_to_float(inv["unit_cost"]).fillna(0)
    if "retail_price" in inv: inv["retail_price"] = _currency_to_float(inv["retail_price"]).fillna(0)
    invg = inv.groupby(["product_name","category"],dropna=False).agg(
        onhandunits=("onhandunits","sum"),
        brand=("brand","first") if "brand" in inv.columns else ("product_name","first"),
        unit_cost=("unit_cost","median") if "unit_cost" in inv.columns else ("onhandunits","size"),
        retail_price=("retail_price","median") if "retail_price" in inv.columns else ("onhandunits","size"),
    ).reset_index()
    sales_name = _detect(sales.columns,["product","productname","name","item","itemname","producttitle"]); sales_qty = _detect(sales.columns,["quantitysold","qtysold","unitssold","quantity","qty","items sold","itemssold"]); sales_cat = _detect(sales.columns,["category","mastercategory","productcategory","department","subcategory"]); sales_date = next((column for column in sales.columns if "date" in column or "time" in column),None)
    if not (sales_name and sales_qty and sales_cat): raise ValueError("Could not detect sales product/quantity/category columns.")
    sales = sales.rename(columns={sales_name:"product_name",sales_qty:"unitssold",sales_cat:"category"}); sales["product_name"] = sales["product_name"].astype(str).str.strip(); sales["category"] = sales["category"].apply(_normalize_category); sales["unitssold"] = pd.to_numeric(sales["unitssold"],errors="coerce").fillna(0)
    if sales_date:
        sales[sales_date] = pd.to_datetime(sales[sales_date],errors="coerce"); latest = sales[sales_date].max()
        if pd.notna(latest): sales = sales[sales[sales_date] >= latest-pd.Timedelta(days=velocity_days)].copy()
    movement = sales.groupby(["product_name","category"],dropna=False)["unitssold"].sum().reset_index(); movement["daily_run_rate"] = movement["unitssold"]/max(velocity_days,1)
    frame = invg.merge(movement,on=["product_name","category"],how="left"); frame["unitssold"] = frame["unitssold"].fillna(0); frame["daily_run_rate"] = frame["daily_run_rate"].fillna(0); frame["days_on_hand"] = np.where(frame["daily_run_rate"]>0,frame["onhandunits"]/frame["daily_run_rate"],UNKNOWN_DOH); frame["inventory_cost"] = frame["onhandunits"]*pd.to_numeric(frame["unit_cost"],errors="coerce").fillna(0); frame["inventory_retail"] = frame["onhandunits"]*pd.to_numeric(frame["retail_price"],errors="coerce").fillna(0)
    overall_daily = frame["daily_run_rate"].mean() if len(frame) else 0
    frame["velocity_band"] = np.where(frame["daily_run_rate"]<=overall_daily*0.5,"Slow",np.where(frame["daily_run_rate"]<=overall_daily*1.2,"Normal","Fast"))
    def decision(row):
        if row["unitssold"]<=0 and row["onhandunits"]>0: return "Dead item"
        if row["days_on_hand"]>=180: return "Aggressive markdown"
        if row["days_on_hand"]>=120: return "Markdown candidate"
        if row["days_on_hand"]>=90: return "Watch closely"
        return "Healthy"
    def discount(row):
        if row["unitssold"]<=0 and row["onhandunits"]>0: return "35%+"
        if row["days_on_hand"]>=180: return "30%"
        if row["days_on_hand"]>=120: return "25%"
        if row["days_on_hand"]>=90: return "15%"
        return "No discount"
    frame["decision"] = frame.apply(decision,axis=1); frame["discount_tier"] = frame.apply(discount,axis=1)
    return frame.sort_values(["days_on_hand","inventory_cost"],ascending=[False,False])


def filter_slow_movers(frame: pd.DataFrame, *, min_doh: float, top_n: int, search: str = "", categories: list[str] | None = None, brands: list[str] | None = None, decisions: list[str] | None = None) -> pd.DataFrame:
    view = frame[frame["days_on_hand"] >= min_doh].copy()
    if categories: view = view[view["category"].isin(categories)]
    if brands and "brand" in view: view = view[view["brand"].isin(brands)]
    if decisions: view = view[view["decision"].isin(decisions)]
    if search.strip(): view = view[view["product_name"].astype(str).str.lower().str.contains(search.strip().lower(),na=False,regex=False)]
    return view.head(max(1,min(int(top_n),500)))


def tier_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty: return pd.DataFrame(columns=["discount_tier","skus","inventory_cost","inventory_retail"])
    return frame.groupby("discount_tier",dropna=False).agg(skus=("product_name","count"),inventory_cost=("inventory_cost","sum"),inventory_retail=("inventory_retail","sum")).reset_index().sort_values("inventory_cost",ascending=False)


def export_excel(frame: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output,engine="openpyxl") as writer: frame.to_excel(writer,index=False,sheet_name="SlowMovers")
    return output.getvalue()
