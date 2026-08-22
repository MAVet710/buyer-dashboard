from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.integrations import IntegrationConfigurationService
from services.doobie_client import DoobieClient
from services.web_buyer_parity import records
from ..auth import RequestContext, get_request_context, get_retail_context
from ..config import Settings, get_settings
from ..database import get_engine
from .buyer_parity import _model

router = APIRouter(prefix="/buyer-parity", tags=["buyer-parity"], dependencies=[Depends(get_retail_context)])


class BuyerSliceRequest(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=64)
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
    _detail, product, _inventory, _sales, inventory_source, sales_source = _model(
        context,
        engine,
        payload.target_doh,
        payload.velocity_adjustment,
        payload.sales_days,
    )
    selected = {value.casefold() for value in payload.categories if value.strip()}
    filtered = product.copy()
    if selected:
        filtered = filtered[filtered["subcategory"].astype(str).str.casefold().isin(selected)].copy()
    if filtered.empty:
        raise HTTPException(422, "No Buyer rows match the selected inventory slice.")
    source = {
        "inventory_filename": inventory_source.filename,
        "sales_filename": sales_source.filename,
        "selected_categories": payload.categories,
        "target_doh": payload.target_doh,
        "velocity_adjustment": payload.velocity_adjustment,
        "sales_days": payload.sales_days,
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
