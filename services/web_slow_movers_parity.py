"""UI-independent exact port of the current app.py Slow Movers workflow."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re
import numpy as np
import pandas as pd

UNKNOWN_DOH=999

def _norm(value):return re.sub(r"[^a-z0-9]","",str(value).lower())
def _detect(columns,aliases):
    mapping={_norm(column):column for column in columns}
    return next((mapping[_norm(alias)] for alias in aliases if _norm(alias) in mapping),None)
def _money(series):return pd.to_numeric(series.astype(str).str.strip().str.replace(r"^\$","",regex=True).str.replace(",","",regex=False),errors="coerce")

def build_slow_movers(inv_raw_df:pd.DataFrame,sales_raw_df:pd.DataFrame,velocity_days:int)->pd.DataFrame:
    inv=inv_raw_df.copy();sales=sales_raw_df.copy();inv.columns=inv.columns.astype(str).str.strip().str.lower();sales.columns=sales.columns.astype(str).str.strip().str.lower()
    iname=_detect(inv.columns,["product","product name","item","item name","name","sku name"]);iqty=_detect(inv.columns,["available","on hand","onhandunits","quantity","qty","quantity on hand","inventory available"]);ibatch=_detect(inv.columns,["batch","batch number","lot","lot number","package id"]);icat=_detect(inv.columns,["category","subcategory","master category","department"]);ibrand=_detect(inv.columns,["brand","brand name","vendor","vendor name","manufacturer","producer","supplier"]);isku=_detect(inv.columns,["sku","sku id","product id","item id"]);icost=_detect(inv.columns,["cost","unit cost","cogs","wholesale","wholesale price","current price"]);iretail=_detect(inv.columns,["med price","retail","retail price","msrp"])
    sname=_detect(sales.columns,["product","product name","item","item name","name","sku name"]);sqty=_detect(sales.columns,["quantity sold","qty sold","units sold","items sold","total inventory sold","quantity","qty"])
    if not(iname and iqty):raise ValueError("Could not detect inventory product/on-hand columns.")
    if not(sname and sqty):raise ValueError("Could not detect sales product/quantity columns.")
    rename={iname:"product_name",iqty:"onhandunits"};
    for source,target in [(ibatch,"batch"),(icat,"category"),(ibrand,"brand"),(isku,"sku"),(icost,"unit_cost"),(iretail,"retail_price")]:
        if source and source not in rename:rename[source]=target
    inv=inv.rename(columns=rename);inv["product_name"]=inv["product_name"].astype(str).str.strip();inv["onhandunits"]=pd.to_numeric(inv["onhandunits"],errors="coerce").fillna(0)
    for column in ["unit_cost","retail_price"]:
        if column in inv:inv[column]=_money(inv[column])
    aggregations={"onhandunits":"sum"}
    for column in ["category","brand","sku","unit_cost","retail_price"]:
        if column in inv:aggregations[column]="first"
    group=["product_name"]+(["batch"] if "batch" in inv else []);inv=inv.groupby(group,dropna=False,as_index=False).agg(aggregations)
    sales=sales.rename(columns={sname:"product_name",sqty:"total_sold"});sales["product_name"]=sales["product_name"].astype(str).str.strip();sales["total_sold"]=pd.to_numeric(sales["total_sold"],errors="coerce").fillna(0);date_col=next((column for column in sales.columns if "date" in column),None);last_sales={};effective=max(int(velocity_days),1)
    if date_col:
        sales[date_col]=pd.to_datetime(sales[date_col],errors="coerce");latest=pd.Timestamp(sales[date_col].max());earliest=pd.Timestamp(sales[date_col].min())
        if pd.notna(latest):
            last_sales=sales.groupby("product_name")[date_col].max().dropna().to_dict();date_range=int((latest-earliest)/pd.Timedelta(1,unit="D")) if pd.notna(earliest) else effective;effective=min(effective,date_range) or effective;sales=sales[sales[date_col]>=latest-pd.DateOffset(days=int(velocity_days))]
    velocity=sales.groupby("product_name",as_index=False)["total_sold"].sum();velocity["daily_run_rate"]=velocity["total_sold"]/max(effective,1);velocity["avg_weekly_sales"]=velocity["daily_run_rate"]*7
    frame=inv.merge(velocity,on="product_name",how="left");frame[["total_sold","daily_run_rate","avg_weekly_sales"]]=frame[["total_sold","daily_run_rate","avg_weekly_sales"]].fillna(0);frame["days_of_supply"]=np.where(frame["daily_run_rate"]>0,frame["onhandunits"]/frame["daily_run_rate"],UNKNOWN_DOH);frame["weeks_of_supply"]=(frame["days_of_supply"]/7).round(1);today=pd.Timestamp.today().normalize();frame["days_since_last_sale"]=frame["product_name"].map(lambda name:int((today-pd.Timestamp(last_sales[name])).days) if name in last_sales else None)
    frame["dollars_on_hand"]=frame["onhandunits"]*frame["unit_cost"] if "unit_cost" in frame else np.nan
    if "retail_price" in frame:frame["retail_dollars_on_hand"]=frame["onhandunits"]*frame["retail_price"]
    def action(row):
        if row.onhandunits<=0:return "⬛ No Stock"
        if row.avg_weekly_sales<=0 or row.days_of_supply>=UNKNOWN_DOH:return "🔴 Investigate"
        if row.days_of_supply>180:return "🔴 Promo / Stop Reorder"
        if row.days_of_supply>120:return "🟠 Markdown"
        if row.days_of_supply>90:return "🟡 Watch"
        if row.days_of_supply>60:return "🟢 Monitor"
        return "✅ Healthy"
    frame["sm_score"]=frame.apply(lambda row:100.0 if row.avg_weekly_sales<=0 else round(min(row.days_of_supply/180,1)*100,1),axis=1);frame["action"]=frame.apply(action,axis=1);frame["suggested_discount"]=frame["days_of_supply"].map(lambda days:"30-50% (Urgent)" if days>180 else "20-30% (High Priority)" if days>120 else "15-20% (Medium Priority)" if days>90 else "10-15% (Low Priority)" if days>60 else "No discount needed");return frame

def filter_slow_movers(frame:pd.DataFrame,*,min_doh:float,top_n:int,search:str="",category:str="All",brand:str="All",sort_by:str="Days of Supply ↓",only_slow:bool=True,exclude_zero:bool=False)->pd.DataFrame:
    view=frame.copy()
    if only_slow:view=view[view["days_of_supply"]>min_doh]
    if exclude_zero:view=view[view["onhandunits"]>0]
    if category!="All" and "category" in view:view=view[view["category"].astype(str)==category]
    if brand!="All" and "brand" in view:view=view[view["brand"].astype(str)==brand]
    if search.strip():
        query=search.strip().casefold();mask=view["product_name"].astype(str).str.casefold().str.contains(query,na=False,regex=False)
        for column in ["sku","brand"]:
            if column in view:mask|=view[column].astype(str).str.casefold().str.contains(query,na=False,regex=False)
        view=view[mask]
    sort_map={"Days of Supply ↓":"days_of_supply","Weeks of Supply ↓":"weeks_of_supply","$ On-Hand ↓":"dollars_on_hand","Days Since Last Sale ↓":"days_since_last_sale"};column=sort_map.get(sort_by,"days_of_supply")
    if column in view:view=view.sort_values(column,ascending=False,na_position="last")
    return view.head(top_n) if top_n>0 else view

def summary(view:pd.DataFrame,min_doh:float)->dict:
    known_doh=view.loc[view["days_of_supply"]!=UNKNOWN_DOH,"days_of_supply"];median=known_doh.median() if not known_doh.empty else np.nan;worst="N/A"
    if not view.empty and "category" in view:
        values=view.groupby("category")["dollars_on_hand"].sum() if view["dollars_on_hand"].notna().any() else view.groupby("category")["onhandunits"].sum();worst=str(values.idxmax()) if not values.empty else "N/A"
    return {"slow_skus":int((view["days_of_supply"]>min_doh).sum()),"units_tied":int(view["onhandunits"].sum()),"median_doh":None if pd.isna(median) else float(median),"dollars_tied":float(view["dollars_on_hand"].sum()) if view["dollars_on_hand"].notna().any() else None,"worst_category":worst}

def tier_summary(frame:pd.DataFrame)->pd.DataFrame:
    if frame.empty:return pd.DataFrame(columns=["Discount Tier","Product Count","Total Units"])
    return frame.groupby("suggested_discount").agg(**{"Product Count":("product_name","count"),"Total Units":("onhandunits","sum")}).reset_index().rename(columns={"suggested_discount":"Discount Tier"})

def export_excel(display:pd.DataFrame,tiers:pd.DataFrame,full:pd.DataFrame)->bytes:
    output=BytesIO()
    with pd.ExcelWriter(output,engine="openpyxl") as writer:display.to_excel(writer,index=False,sheet_name="Slow Movers");tiers.to_excel(writer,index=False,sheet_name="Summary");full.replace(UNKNOWN_DOH,np.nan).to_excel(writer,index=False,sheet_name="Full Detail")
    return output.getvalue()

def export_filename()->str:return f"slow_movers_{datetime.now():%Y%m%d}.xlsx"
