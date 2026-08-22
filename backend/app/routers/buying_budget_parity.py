from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from services.web_buying_budget_parity import build_budget
from services.web_buyer_parity import read_tabular_bytes
from modules.data_hub_repository import DataHubRepository
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/buying-budget-parity", tags=["buying-budget-parity"], dependencies=[Depends(get_retail_context)])


def _sources(context: RequestContext, engine: Engine):
    sources = {row.dataset_key: row for row in DataHubRepository(engine).list_active_sources(context.organization_id, context.facility_id)}
    inventory = sources.get("inventory") or sources.get("sandbox_buyer_inventory")
    sales = sources.get("product_sales") or sources.get("sandbox_buyer_sales") or sources.get("sandbox_delivery_sales")
    if inventory is None or sales is None:
        raise HTTPException(422, "Buying Budget needs active Inventory and Product Sales data in Data & Settings.")
    return read_tabular_bytes(inventory.payload, inventory.filename), read_tabular_bytes(sales.payload, sales.filename)


@router.get("")
def buying_budget(
    selected_days: int = Query(30),
    target_dos: float = Query(45, ge=1),
    cogs_pct: float = Query(50, ge=0, le=100),
    safety_stock_pct: float = Query(10, ge=0, le=200),
    growth_adj_pct: float = Query(0, ge=-100, le=300),
    include_dead: bool = False,
    include_quarantine: bool = False,
    include_accessories: bool = False,
    on_order_cost: float = Query(0, ge=0),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if selected_days not in {14, 30, 60, 90}:
        raise HTTPException(422, "Planning sales window must be 14, 30, 60, or 90 days.")
    inventory, sales = _sources(context, engine)
    try:
        return build_budget(
            inventory,
            sales,
            selected_days=selected_days,
            target_dos=target_dos,
            cogs_pct=cogs_pct / 100,
            safety_stock=safety_stock_pct / 100,
            growth_adj=growth_adj_pct / 100,
            include_dead=include_dead,
            include_quarantine=include_quarantine,
            include_accessories=include_accessories,
            on_order_cost=on_order_cost,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
