from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import Engine

from delivery_impact import (
    build_time_series,
    build_wow_time_series,
    compute_delivery_kpis,
    compute_weekday_wow_kpis,
    match_manifest_to_sales,
    parse_manifest_csv_xlsx_bytes,
    parse_manifest_pdf_bytes,
    parse_sales_report_bytes,
)
from modules.data_hub_repository import DataHubRepository, PublishedSource
from services.web_buyer_parity import (
    PRODUCT_TABLE_DISPLAY_LIMIT,
    build_forecast,
    buyer_intelligence,
    category_dos,
    forecast_view,
    read_tabular_bytes,
    records,
    sku_inventory_view,
    trends,
    xlsx_bytes,
)
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/buyer-parity", tags=["buyer-parity"], dependencies=[Depends(get_retail_context)])
_INVENTORY_KEYS = ("inventory", "sandbox_buyer_inventory")
_SALES_KEYS = ("product_sales", "sandbox_buyer_sales", "sandbox_delivery_sales")
_MAX_UPLOAD = 20 * 1024 * 1024


def _pick(sources: list[PublishedSource], keys: tuple[str, ...]) -> PublishedSource | None:
    by_key = {row.dataset_key: row for row in sources}
    return next((by_key[key] for key in keys if key in by_key), None)


def _inputs(context: RequestContext, engine: Engine):
    sources = DataHubRepository(engine).list_active_sources(context.organization_id, context.facility_id)
    inventory_source = _pick(sources, _INVENTORY_KEYS); sales_source = _pick(sources, _SALES_KEYS)
    if inventory_source is None or sales_source is None:
        missing = []
        if inventory_source is None: missing.append("Inventory")
        if sales_source is None: missing.append("Product Sales")
        raise HTTPException(422, f"Buyer Operations needs active {' and '.join(missing)} data in Data & Settings before this workspace can run.")
    try:
        inventory = read_tabular_bytes(inventory_source.payload, inventory_source.filename); sales = read_tabular_bytes(sales_source.payload, sales_source.filename)
    except Exception as exc:
        raise HTTPException(422, f"The active Buyer Operations sources could not be read: {exc}") from exc
    return inventory, sales, inventory_source, sales_source


def _model(context: RequestContext, engine: Engine, target_doh: int, velocity_adjustment: float, sales_days: int):
    inventory, sales, inventory_source, sales_source = _inputs(context, engine)
    try:
        detail, product, inv_normalized, sales_normalized = build_forecast(inventory, sales, doh_threshold=target_doh, velocity_adjustment=velocity_adjustment, sales_period_days=sales_days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return detail, product, inv_normalized, sales_normalized, inventory_source, sales_source


@router.get("/dashboard")
def dashboard(target_doh: int = Query(21, ge=1, le=120), velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0), sales_days: int = Query(60, ge=7, le=120), sku_window: int = Query(56, ge=7, le=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    detail, product, inv_normalized, sales_normalized, inventory_source, sales_source = _model(context, engine, target_doh, velocity_adjustment, sales_days)
    categories = category_dos(detail, product); forecast = forecast_view(detail, product); sku = sku_inventory_view(inv_normalized, sales_normalized, sku_window)
    reorder = sku[sku["days_of_supply"] <= 21] if not sku.empty else sku
    overstock = sku[sku["days_of_supply"] >= 90] if not sku.empty else sku
    expiring = sku[sku["days_to_expire"].notna() & (sku["days_to_expire"] < 60)] if not sku.empty and "days_to_expire" in sku else sku.iloc[0:0]
    total_units = float(detail["unitssold"].sum()) if "unitssold" in detail else 0.0; reorder_asap = int((detail.get("reorderpriority") == "1 – Reorder ASAP").sum()) if "reorderpriority" in detail else 0
    return {"controls":{"target_doh":target_doh,"velocity_adjustment":velocity_adjustment,"sales_days":sales_days,"sku_window":sku_window},"summary":{"units_sold":total_units,"reorder_asap":reorder_asap,"tracked_products":int(len(product)),"categories":int(detail["subcategory"].nunique()) if "subcategory" in detail else 0},"sources":{"inventory":{"filename":inventory_source.filename,"rows":inventory_source.row_count,"activated_at":inventory_source.activated_at},"sales":{"filename":sales_source.filename,"rows":sales_source.row_count,"activated_at":sales_source.activated_at}},"category_dos":records(categories),"forecast":records(forecast),"product_rows":records(product.sort_values("unitssold",ascending=False) if "unitssold" in product else product,limit=PRODUCT_TABLE_DISPLAY_LIMIT),"product_rows_total":int(len(product)),"sku_views":{"all":records(sku),"reorder":records(reorder),"overstock":records(overstock),"expiring":records(expiring)}}


@router.get("/trends")
def buyer_trends(target_doh: int = Query(21, ge=1, le=120), velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0), sales_days: int = Query(60, ge=7, le=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _detail, product, _inv, sales, _inventory_source, _sales_source = _model(context, engine, target_doh, velocity_adjustment, sales_days); output = trends(product, sales)
    return {"sales_days":sales_days, **{name:records(frame,limit=500) for name,frame in output.items()}}


@router.get("/intelligence")
def intelligence(target_doh: int = Query(21, ge=1, le=120), velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0), sales_days: int = Query(60, ge=7, le=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _detail, product, _inv, _sales, _inventory_source, _sales_source = _model(context, engine, target_doh, velocity_adjustment, sales_days); result = buyer_intelligence(product)
    return {"sales_days":sales_days,"summary":result["summary"],"purchase_priorities":records(result["purchase_priorities"]),"sku_risk":records(result["sku_risk"]),"overstock_watch":records(result["overstock_watch"]),"category_risk":records(result["category_risk"])}


def _filter_export_frame(frame: pd.DataFrame, categories: list[str], *, reorder_only: bool = False) -> pd.DataFrame:
    filtered = frame.copy()
    selected = {str(value).strip().casefold() for value in categories if str(value).strip()}
    if selected and "subcategory" in filtered:
        filtered = filtered[filtered["subcategory"].astype(str).str.casefold().isin(selected)].copy()
    if reorder_only and "reorderpriority" in filtered:
        filtered = filtered[filtered["reorderpriority"] == "1 – Reorder ASAP"].copy()
    return filtered


@router.get("/export")
def export(kind: str = Query("forecast", pattern="^(forecast|product|sku)$"), target_doh: int = Query(21, ge=1, le=120), velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0), sales_days: int = Query(60, ge=7, le=120), sku_window: int = Query(56, ge=7, le=120), category: list[str] = Query(default=[]), reorder_only: bool = False, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    detail, product, inv_normalized, sales_normalized, _inventory_source, _sales_source = _model(context, engine, target_doh, velocity_adjustment, sales_days)
    if kind == "forecast": frame,filename,sheet = _filter_export_frame(forecast_view(detail,product),category,reorder_only=reorder_only),"forecast_table.xlsx","Forecast"
    elif kind == "product": frame,filename,sheet = _filter_export_frame((product.sort_values("unitssold",ascending=False).head(PRODUCT_TABLE_DISPLAY_LIMIT) if "unitssold" in product else product.head(PRODUCT_TABLE_DISPLAY_LIMIT)),category),"product_level_forecast.xlsx","Product Rows"
    else: frame,filename,sheet = sku_inventory_view(inv_normalized,sales_normalized,sku_window),"sku_inventory_buyer_view.xlsx","SKU Buyer View"
    return Response(content=xlsx_bytes(frame,sheet),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="{filename}"'})


def _safe_number(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)): return None
    return value


def _kpi_json(payload: dict) -> dict:
    output = {}
    for key,value in payload.items():
        if isinstance(value,pd.DataFrame): output[key] = records(value)
        elif isinstance(value,pd.Timestamp): output[key] = value.isoformat()
        else: output[key] = _safe_number(value)
    return output


def _series(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty: return []
    result = frame.copy()
    if "period" in result: result["period"] = pd.to_datetime(result["period"],errors="coerce").map(lambda value: value.isoformat() if pd.notna(value) else None)
    return records(result)


@router.post("/delivery-impact")
async def delivery_impact_upload(
    manifest: UploadFile = File(...),
    sales: UploadFile = File(...),
    received_at: str = Form(""),
    window_days: int = Form(14),
    fuzzy_threshold: float = Form(0.82),
):
    manifest_bytes = await manifest.read(_MAX_UPLOAD + 1); sales_bytes = await sales.read(_MAX_UPLOAD + 1)
    if not manifest_bytes or not sales_bytes: raise HTTPException(422,"Both a delivery manifest and sales report are required.")
    if len(manifest_bytes) > _MAX_UPLOAD or len(sales_bytes) > _MAX_UPLOAD: raise HTTPException(413,"Delivery Impact files must be 20 MB or smaller.")
    if window_days < 1 or window_days > 60: raise HTTPException(422,"Comparison window must be between 1 and 60 days.")
    if fuzzy_threshold < 0.5 or fuzzy_threshold > 1: raise HTTPException(422,"Fuzzy match threshold must be between 0.5 and 1.0.")
    try:
        sales_df = parse_sales_report_bytes(sales_bytes, sales.filename or "sales.csv")
        if (manifest.filename or "").casefold().endswith(".pdf"):
            delivery_dt, items, raw_text = parse_manifest_pdf_bytes(manifest_bytes, manifest.filename or "manifest.pdf")
        else:
            delivery_dt, items, raw_text = parse_manifest_csv_xlsx_bytes(manifest_bytes, manifest.filename or "manifest.csv")
        if received_at.strip(): delivery_dt = pd.Timestamp(received_at)
        if delivery_dt is None or pd.isna(delivery_dt): raise ValueError("No delivery received date was found. Enter the received date/time and run the analysis again.")
        if items.empty: raise ValueError("No manifest item rows could be detected.")
        sales_names = sales_df["product_name"].dropna().astype(str).drop_duplicates().tolist(); matched, unmatched = match_manifest_to_sales(items["item_name"].astype(str).tolist(), sales_names, fuzzy_threshold=fuzzy_threshold); delivered_names = list(dict.fromkeys(matched.values()))
        kpis = compute_delivery_kpis(sales_df, pd.Timestamp(delivery_dt), window_days=window_days, delivered_names=delivered_names); wow = compute_weekday_wow_kpis(sales_df, pd.Timestamp(delivery_dt), delivered_names=delivered_names); daily = build_time_series(sales_df,pd.Timestamp(delivery_dt),window_days=window_days,granularity="daily",delivered_names=delivered_names); hourly = build_time_series(sales_df,pd.Timestamp(delivery_dt),window_days=window_days,granularity="hourly",delivered_names=delivered_names); wow_delivery,wow_prior = build_wow_time_series(sales_df,pd.Timestamp(delivery_dt),granularity="hourly",delivered_names=delivered_names)
    except Exception as exc:
        raise HTTPException(422,f"Delivery Impact could not process these files: {exc}") from exc
    return {"received_at":pd.Timestamp(delivery_dt).isoformat(),"window_days":window_days,"manifest_filename":manifest.filename,"sales_filename":sales.filename,"manifest_items":records(items),"matched":matched,"unmatched":unmatched,"matched_count":len(matched),"unmatched_count":len(unmatched),"kpis":_kpi_json(kpis),"weekday_wow":_kpi_json(wow),"daily_series":_series(daily),"hourly_series":_series(hourly),"wow_delivery_series":_series(wow_delivery),"wow_prior_series":_series(wow_prior),"debug_text":raw_text}
