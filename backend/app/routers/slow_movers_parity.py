from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import Engine

from modules.data_hub_repository import DataHubRepository
from services.web_buyer_parity import read_tabular_bytes, records
from services.web_slow_movers_parity import build_slow_movers, export_excel, filter_slow_movers, tier_summary
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/slow-movers-parity", tags=["slow-movers-parity"], dependencies=[Depends(get_retail_context)])


def _frames(context: RequestContext, engine: Engine):
    sources = {row.dataset_key: row for row in DataHubRepository(engine).list_active_sources(context.organization_id, context.facility_id)}
    inventory = sources.get("inventory") or sources.get("sandbox_buyer_inventory")
    sales = sources.get("product_sales") or sources.get("sandbox_buyer_sales") or sources.get("sandbox_delivery_sales")
    if inventory is None or sales is None:
        raise HTTPException(422, "Slow Movers needs active Inventory and Product Sales data in Data & Settings.")
    return read_tabular_bytes(inventory.payload, inventory.filename), read_tabular_bytes(sales.payload, sales.filename)


def _view(context: RequestContext, engine: Engine, velocity_days: int, min_doh: float, top_n: int, search: str, category: list[str], brand: list[str], decision: list[str]):
    inventory, sales = _frames(context, engine)
    try:
        all_rows = build_slow_movers(inventory, sales, velocity_days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    view = filter_slow_movers(all_rows, min_doh=min_doh, top_n=top_n, search=search, categories=category, brands=brand, decisions=decision)
    return all_rows, view


@router.get("")
def slow_movers(
    velocity_days: int = Query(56),
    min_doh: float = Query(90, ge=0),
    top_n: int = Query(100, ge=1, le=500),
    search: str = "",
    category: list[str] = Query(default=[]),
    brand: list[str] = Query(default=[]),
    decision: list[str] = Query(default=[]),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if velocity_days not in {14, 28, 56, 84}:
        raise HTTPException(422, "Velocity window must be 14, 28, 56, or 84 days.")
    all_rows, view = _view(context, engine, velocity_days, min_doh, top_n, search, category, brand, decision)
    tiers = tier_summary(view)
    return {
        "controls": {"velocity_days": velocity_days, "min_doh": min_doh, "top_n": top_n, "search": search},
        "facets": {
            "categories": sorted(all_rows["category"].dropna().astype(str).unique().tolist()),
            "brands": sorted(all_rows["brand"].dropna().astype(str).unique().tolist()) if "brand" in all_rows else [],
            "decisions": sorted(all_rows["decision"].dropna().astype(str).unique().tolist()),
        },
        "summary": {
            "slow_skus": int(len(view)),
            "inventory_cost": float(view["inventory_cost"].sum()),
            "dead_items": int((view["decision"] == "Dead item").sum()),
            "markdown_candidates": int(view["decision"].isin(["Markdown candidate", "Aggressive markdown"]).sum()),
        },
        "discount_tiers": records(tiers),
        "items": records(view),
    }


@router.get("/export")
def slow_movers_export(
    velocity_days: int = Query(56),
    min_doh: float = Query(90, ge=0),
    top_n: int = Query(100, ge=1, le=500),
    search: str = "",
    category: list[str] = Query(default=[]),
    brand: list[str] = Query(default=[]),
    decision: list[str] = Query(default=[]),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if velocity_days not in {14, 28, 56, 84}:
        raise HTTPException(422, "Velocity window must be 14, 28, 56, or 84 days.")
    _all_rows, view = _view(context, engine, velocity_days, min_doh, top_n, search, category, brand, decision)
    columns = [column for column in ["decision", "discount_tier", "product_name", "brand", "category", "onhandunits", "unitssold", "daily_run_rate", "days_on_hand", "inventory_cost", "inventory_retail", "velocity_band"] if column in view]
    return Response(content=export_excel(view[columns]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="slow_movers.xlsx"'})
