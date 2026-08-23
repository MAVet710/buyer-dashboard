from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from services.doobie_client import DoobieClient
from services.web_buyer_parity import records, sku_inventory_view
from ..auth import RequestContext, get_request_context, get_retail_context
from ..config import Settings, get_settings
from ..database import get_engine
from .buyer_parity import _model

router = APIRouter(prefix="/buyer-parity", tags=["buyer-parity"], dependencies=[Depends(get_retail_context)])


class BuyerSliceRequest(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=64)
    brands: list[str] = Field(default_factory=list, max_length=128)
    search: str = Field(default="", max_length=240)
    expiration_window: str = Field(default="Any", max_length=32)
    on_hand_only: bool = True
    min_doh: float = Field(default=0, ge=0, le=9999)
    max_doh: float = Field(default=9999, ge=0, le=9999)
    velocity_window: int = Field(default=56, ge=7, le=120)
    top_n: int = Field(default=0, ge=0, le=5000)
    sort_by: str = Field(default="dollars_on_hand_desc", max_length=64)
    target_doh: int = Field(default=21, ge=1, le=120)
    velocity_adjustment: float = Field(default=0.5, ge=0.01, le=5.0)
    sales_days: int = Field(default=60, ge=7, le=120)
    state: str = Field(default="MA", max_length=64)


class InventoryCheckRequest(BuyerSliceRequest):
    question: str = Field(default="Which inventory risks need immediate attention?", max_length=2000)


class BuyerBriefRequest(BuyerSliceRequest):
    question: str = Field(default="What should I reorder right now with quantities?", max_length=2000)


def _platform_doobie(engine: Engine, settings: Settings) -> DoobieClient:
    try:
        service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
        row = service.get("platform", "global", "doobie")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if row is None:
        raise HTTPException(503, "Doobie is not configured. Level DEV must configure the platform Doobie integration.")
    configuration = service.public(row).get("configuration") or {}
    return DoobieClient(
        base_url=str(configuration.get("base_url") or "").strip().rstrip("/"),
        api_key=service.secret(row),
        timeout_seconds=12,
    )


def _buyer_slice(payload: BuyerSliceRequest, context: RequestContext, engine: Engine):
    _detail, product, inventory, sales, inventory_source, sales_source = _model(
        context,
        engine,
        payload.target_doh,
        payload.velocity_adjustment,
        payload.sales_days,
    )

    filtered = sku_inventory_view(inventory, sales, payload.velocity_window).copy()
    if not product.empty and "product_name" in filtered and "product_name" in product:
        context_columns = [
            column
            for column in ["product_name", "strain_type", "packagesize", "reorderqty", "reorderpriority", "unitssold", "avgunitsperday"]
            if column in product
        ]
        if len(context_columns) > 1:
            product_context = product[context_columns].drop_duplicates(subset=["product_name"], keep="first")
            filtered = filtered.merge(product_context, on="product_name", how="left", suffixes=("", "_forecast"))

    if "days_of_supply" in filtered:
        filtered["days_of_supply"] = pd.to_numeric(filtered["days_of_supply"], errors="coerce").fillna(999)
    if "daily_run_rate" in filtered:
        daily_rate = pd.to_numeric(filtered["daily_run_rate"], errors="coerce").fillna(0)
        days_supply = pd.to_numeric(filtered.get("days_of_supply", 999), errors="coerce").fillna(999)
        filtered["recommended_reorder_qty"] = np.ceil(
            (float(payload.target_doh) - days_supply).clip(lower=0) * daily_rate
        ).astype(int)

    selected_categories = {value.casefold() for value in payload.categories if value.strip()}
    if selected_categories and "category" in filtered:
        filtered = filtered[filtered["category"].astype(str).str.casefold().isin(selected_categories)].copy()

    selected_brands = {value.casefold() for value in payload.brands if value.strip()}
    if selected_brands and "brand_vendor" in filtered:
        filtered = filtered[filtered["brand_vendor"].astype(str).str.casefold().isin(selected_brands)].copy()

    search = payload.search.strip().casefold()
    if search:
        haystack = pd.Series("", index=filtered.index, dtype="object")
        for column in ["sku", "product_name", "brand_vendor"]:
            if column in filtered:
                haystack = haystack + " " + filtered[column].fillna("").astype(str).str.casefold()
        filtered = filtered[haystack.str.contains(search, regex=False, na=False)].copy()

    on_hand = pd.to_numeric(filtered.get("onhandunits", 0), errors="coerce").fillna(0)
    if payload.on_hand_only:
        filtered = filtered[on_hand > 0].copy()

    if "days_of_supply" in filtered:
        doh = pd.to_numeric(filtered["days_of_supply"], errors="coerce").fillna(999)
        filtered = filtered[(doh >= payload.min_doh) & (doh <= payload.max_doh)].copy()

    expiration_window = payload.expiration_window.strip().casefold()
    if expiration_window != "any" and "days_to_expire" in filtered:
        days_to_expire = pd.to_numeric(filtered["days_to_expire"], errors="coerce")
        if expiration_window == "expired":
            filtered = filtered[days_to_expire.notna() & (days_to_expire < 0)].copy()
        else:
            window_days = {"30 days": 30, "60 days": 60, "90 days": 90}.get(expiration_window)
            if window_days is not None:
                filtered = filtered[days_to_expire.notna() & (days_to_expire >= 0) & (days_to_expire <= window_days)].copy()

    sort_columns = {
        "dollars_on_hand_desc": ("dollars_on_hand", False),
        "days_of_supply_asc": ("days_of_supply", True),
        "days_of_supply_desc": ("days_of_supply", False),
        "weekly_sales_desc": ("avg_weekly_sales", False),
        "on_hand_desc": ("onhandunits", False),
        "expiration_asc": ("days_to_expire", True),
    }
    sort_column, ascending = sort_columns.get(payload.sort_by, ("dollars_on_hand", False))
    if sort_column in filtered:
        filtered = filtered.sort_values(sort_column, ascending=ascending, na_position="last")
    if payload.top_n:
        filtered = filtered.head(payload.top_n)

    if filtered.empty:
        raise HTTPException(422, "No Buyer rows match the selected inventory slice.")

    source = {
        "inventory_filename": inventory_source.filename,
        "sales_filename": sales_source.filename,
        "selected_categories": payload.categories,
        "selected_brands": payload.brands,
        "search": payload.search,
        "expiration_window": payload.expiration_window,
        "on_hand_only": payload.on_hand_only,
        "minimum_doh": payload.min_doh,
        "maximum_doh": payload.max_doh,
        "velocity_window": payload.velocity_window,
        "top_n": payload.top_n or "All",
        "sort_by": payload.sort_by,
        "target_doh": payload.target_doh,
        "velocity_adjustment": payload.velocity_adjustment,
        "sales_days": payload.sales_days,
        "filtered_rows": int(len(filtered)),
    }
    return filtered, source


@router.get("/drilldown")
def sku_drilldown(
    category: str = Query(..., min_length=1, max_length=160),
    size: str = Query("unspecified", max_length=80),
    strain_type: str = Query("unspecified", max_length=160),
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _detail, _product, inventory, sales, _inventory_source, _sales_source = _model(
        context,
        engine,
        target_doh,
        velocity_adjustment,
        sales_days,
    )
    sales_slice = sales[(sales["mastercategory"] == category) & (sales["packagesize"] == size)].copy()
    if strain_type.casefold() != "unspecified":
        sales_slice = sales_slice[sales_slice["strain_type"].astype(str).str.casefold() == strain_type.casefold()]

    sku_rows = pd.DataFrame()
    if not sales_slice.empty:
        has_batch = "batch_id" in sales_slice.columns
        has_package = "package_id" in sales_slice.columns
        has_net_sales = "net_sales" in sales_slice.columns
        has_sku = "sku" in sales_slice.columns
        group_cols = ["product_name"]
        if has_batch:
            group_cols.append("batch_id")
        if has_package:
            group_cols.append("package_id")
        aggregations: dict[str, str] = {"unitssold": "sum"}
        if has_net_sales:
            aggregations["net_sales"] = "sum"
        if has_sku:
            aggregations["sku"] = "first"
        sku_rows = sales_slice.groupby(group_cols, dropna=False).agg(aggregations).reset_index()
        sku_rows["est_units_per_day"] = (
            pd.to_numeric(sku_rows["unitssold"], errors="coerce").fillna(0) / max(int(sales_days), 1)
        ) * float(velocity_adjustment)
        visible = ["product_name"]
        if has_batch:
            visible.append("batch_id")
        if has_package:
            visible.append("package_id")
        visible.append("unitssold")
        if has_net_sales:
            visible.append("net_sales")
        visible.append("est_units_per_day")
        if has_sku:
            visible.append("sku")
        sku_rows = sku_rows[visible].sort_values("est_units_per_day", ascending=False).head(50)

    inventory_slice = inventory[(inventory["subcategory"] == category) & (inventory["packagesize"] == size)].copy()
    if strain_type.casefold() != "unspecified":
        inventory_slice = inventory_slice[inventory_slice["strain_type"].astype(str).str.casefold() == strain_type.casefold()]
    batch_rows = pd.DataFrame()
    if not inventory_slice.empty and "batch" in inventory_slice.columns:
        batch_rows = (
            inventory_slice.groupby("batch", dropna=False)["onhandunits"]
            .sum()
            .reset_index()
            .rename(columns={"onhandunits": "batch_onhandunits"})
            .sort_values("batch_onhandunits", ascending=False)
        )
    return {"sku_rows": records(sku_rows), "batch_rows": records(batch_rows)}


@router.post("/inventory-check")
def inventory_check(
    payload: InventoryCheckRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    filtered, source = _buyer_slice(payload, context, engine)
    response = _platform_doobie(engine, settings).inventory_check(
        {"inventory": records(filtered, limit=2000), "source": source},
        state=payload.state,
        question=payload.question,
    )
    if response.get("mode") == "fallback":
        raise HTTPException(503, str(response.get("answer") or response.get("error") or "Doobie is unavailable."))
    return response


@router.post("/buyer-brief")
def buyer_brief(
    payload: BuyerBriefRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    filtered, source = _buyer_slice(payload, context, engine)
    response = _platform_doobie(engine, settings).buyer_brief(
        {"inventory": records(filtered, limit=2000), "source": source},
        state=payload.state,
        question=payload.question,
    )
    if response.get("mode") == "fallback":
        raise HTTPException(503, str(response.get("answer") or response.get("error") or "Doobie is unavailable."))
    return response
