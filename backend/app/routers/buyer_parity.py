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
    normalize_sales_report_dataframe,
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
    exact_buyer_intelligence,
    exact_trends,
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


def _require_available_data_mode(context: RequestContext) -> None:
    if context.data_mode == "Dutchie Live":
        raise HTTPException(
            503,
            "Dutchie Live is selected, but live data fetch is not yet implemented. Switch to Uploads or complete the Dutchie API integration.",
        )


def _inputs(context: RequestContext, engine: Engine):
    _require_available_data_mode(context)
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
    return {"data_mode":context.data_mode,"controls":{"target_doh":target_doh,"velocity_adjustment":velocity_adjustment,"sales_days":sales_days,"sku_window":sku_window},"summary":{"units_sold":total_units,"reorder_asap":reorder_asap,"tracked_products":int(len(product)),"categories":int(detail["subcategory"].nunique()) if "subcategory" in detail else 0},"sources":{"inventory":{"filename":inventory_source.filename,"rows":inventory_source.row_count,"activated_at":inventory_source.activated_at},"sales":{"filename":sales_source.filename,"rows":sales_source.row_count,"activated_at":sales_source.activated_at}},"category_dos":records(categories),"forecast":records(forecast),"product_rows":records(product.sort_values("unitssold",ascending=False) if "unitssold" in product else product,limit=PRODUCT_TABLE_DISPLAY_LIMIT),"product_rows_total":int(len(product)),"sku_views":{"all":records(sku),"reorder":records(reorder),"overstock":records(overstock),"expiring":records(expiring)}}


@router.get("/trends")
def buyer_trends(trend_days: int = Query(30, ge=7, le=120), compare_days: int = Query(30, ge=7, le=120), run_rate_multiplier: float = Query(1.0, ge=0.1, le=3.0), top_n: int = Query(10, ge=1, le=50), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _detail, product, _inv, sales, _inventory_source, _sales_source = _model(context, engine, 21, run_rate_multiplier, trend_days); output = exact_trends(product,sales,trend_days,compare_days,run_rate_multiplier,top_n)
    return {"controls":{"trend_days":trend_days,"compare_days":compare_days,"run_rate_multiplier":run_rate_multiplier,"top_n":top_n}, **{name:records(frame,limit=500) for name,frame in output.items()}}


@router.get("/intelligence")
def intelligence(lookback_days: int = Query(60, ge=14, le=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _detail, product, _inv, sales, _inventory_source, _sales_source = _model(context, engine, 21, 1.0, lookback_days); result=exact_buyer_intelligence(product,sales,lookback_days)
    return {"lookback_days":lookback_days,"summary":result["summary"],"by_category":records(result["by_category"],limit=20),"by_product":records(result["by_product"],limit=200),"purchase_priorities":records(result["purchase_priorities"])}


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


def _active_delivery_sales(context: RequestContext, engine: Engine) -> tuple[pd.DataFrame, str]:
    _require_available_data_mode(context)
    sources = DataHubRepository(engine).list_active_sources(context.organization_id, context.facility_id)
    source = _pick(sources, _SALES_KEYS)
    if source is None:
        raise HTTPException(422, "No active Buyer Dashboard sales data is available. Upload a sales report or publish Product Sales in Data & Settings.")
    try:
        return normalize_sales_report_dataframe(read_tabular_bytes(source.payload, source.filename)), "Buyer Dashboard sales data"
    except Exception as exc:
        raise HTTPException(422, f"The active Buyer Dashboard sales data could not be read: {exc}") from exc


def _delivery_manifest_result(items: pd.DataFrame, raw_text: str, filename: str, received_at: pd.Timestamp, sales_df: pd.DataFrame, sales_names: list[str], window_days: int, fuzzy_threshold: float, delivered_names: list[str] | None = None) -> dict:
    matched, unmatched = match_manifest_to_sales(items["item_name"].dropna().astype(str).tolist(), sales_names, fuzzy_threshold=fuzzy_threshold)
    delivered = delivered_names if delivered_names is not None else list(dict.fromkeys(matched.values()))
    kpis = compute_delivery_kpis(sales_df, received_at, window_days=window_days, delivered_names=delivered or None)
    wow = compute_weekday_wow_kpis(sales_df, received_at, delivered_names=delivered or None)
    daily = build_time_series(sales_df, received_at, window_days=window_days, granularity="daily", delivered_names=delivered or None)
    hourly = build_time_series(sales_df, received_at, window_days=window_days, granularity="hourly", delivered_names=delivered or None)
    wow_daily, wow_prior_daily = build_wow_time_series(sales_df, received_at, granularity="daily", delivered_names=delivered or None)
    wow_hourly, wow_prior_hourly = build_wow_time_series(sales_df, received_at, granularity="hourly", delivered_names=delivered or None)
    return {"filename":filename,"received_at":received_at.isoformat(),"items":records(items),"debug_text":raw_text,"matched":matched,"unmatched":unmatched,"kpis":_kpi_json(kpis),"weekday_wow":_kpi_json(wow),"daily_series":_series(daily),"hourly_series":_series(hourly),"wow_daily_series":_series(wow_daily),"wow_prior_daily_series":_series(wow_prior_daily),"wow_hourly_series":_series(wow_hourly),"wow_prior_hourly_series":_series(wow_prior_hourly)}


@router.post("/delivery-impact-workspace")
async def delivery_impact_workspace(
    manifests: list[UploadFile] = File(...),
    sales: UploadFile | None = File(None),
    use_active_sales: bool = Form(True),
    window_days: int = Form(14),
    fuzzy_threshold: float = Form(0.82),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if not manifests: raise HTTPException(422,"Upload one or more manifest files.")
    if len(manifests)>25: raise HTTPException(422,"Upload no more than 25 manifests at once.")
    if window_days not in {7,14,21,28}: raise HTTPException(422,"Comparison window must be 7, 14, 21, or 28 days.")
    if fuzzy_threshold<0.60 or fuzzy_threshold>1: raise HTTPException(422,"Fuzzy match threshold must be between 0.60 and 1.00.")
    if use_active_sales:
        sales_df, sales_label = _active_delivery_sales(context,engine)
    else:
        if sales is None: raise HTTPException(422,"Upload a sales report or enable Buyer Dashboard sales reuse.")
        sales_bytes=await sales.read(_MAX_UPLOAD+1)
        if not sales_bytes: raise HTTPException(422,"The sales report is empty.")
        if len(sales_bytes)>_MAX_UPLOAD: raise HTTPException(413,"The sales report exceeds the 20 MB limit.")
        try:sales_df=parse_sales_report_bytes(sales_bytes,sales.filename or "sales.csv")
        except Exception as exc:raise HTTPException(422,f"The sales report could not be parsed: {exc}") from exc
        sales_label=sales.filename or "sales.csv"
    if sales_df.empty: raise HTTPException(422,"No usable sales rows were found. Ensure the source has Order Time and Net Sales columns.")
    sales_names=sales_df["product_name"].dropna().astype(str).drop_duplicates().tolist();parsed=[];invalid=[]
    for upload in manifests:
        body=await upload.read(_MAX_UPLOAD+1);filename=upload.filename or "manifest"
        if len(body)>_MAX_UPLOAD: invalid.append({"filename":filename,"reason":"File exceeds the 20 MB limit."});continue
        try:
            if filename.casefold().endswith(".pdf"):received,items,debug=parse_manifest_pdf_bytes(body,filename)
            else:received,items,debug=parse_manifest_csv_xlsx_bytes(body,filename)
            received=pd.to_datetime(received,errors="coerce")
            if pd.isna(received):invalid.append({"filename":filename,"reason":"No detectable received date/time.","debug_text":debug});continue
            if items.empty:invalid.append({"filename":filename,"reason":"No manifest item rows could be detected.","debug_text":debug});continue
            parsed.append((items,debug,filename,pd.Timestamp(received)))
        except Exception as exc:invalid.append({"filename":filename,"reason":str(exc)})
    if not parsed:raise HTTPException(422,"None of the uploaded manifests contained a usable received date and item table.")
    combined_delivered=[]
    for items, _debug, _filename, _received in parsed:
        matched,_unmatched=match_manifest_to_sales(items["item_name"].dropna().astype(str).tolist(),sales_names,fuzzy_threshold=fuzzy_threshold)
        for name in matched.values():
            if name not in combined_delivered:combined_delivered.append(name)
    results=[]
    combined_keys=("kpis","weekday_wow","daily_series","hourly_series","wow_daily_series","wow_prior_daily_series","wow_hourly_series","wow_prior_hourly_series")
    for items,debug,filename,received in parsed:
        result=_delivery_manifest_result(items,debug,filename,received,sales_df,sales_names,window_days,fuzzy_threshold)
        combined=_delivery_manifest_result(items,debug,filename,received,sales_df,sales_names,window_days,fuzzy_threshold,combined_delivered or None)
        for key in combined_keys:result[f"combined_{key}"]=combined[key]
        results.append(result)
    return {"sales_source":sales_label,"sales_rows":int(len(sales_df)),"sales_days":int(sales_df["order_time"].dt.date.nunique()),"sales_products":int(len(sales_names)),"window_days":window_days,"fuzzy_threshold":fuzzy_threshold,"manifests":results,"invalid_manifests":invalid}
