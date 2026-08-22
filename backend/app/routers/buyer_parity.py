from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import Engine

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

router = APIRouter(
    prefix="/buyer-parity",
    tags=["buyer-parity"],
    dependencies=[Depends(get_retail_context)],
)

_INVENTORY_KEYS = ("inventory", "sandbox_buyer_inventory")
_SALES_KEYS = ("product_sales", "sandbox_buyer_sales", "sandbox_delivery_sales")


def _pick(sources: list[PublishedSource], keys: tuple[str, ...]) -> PublishedSource | None:
    by_key = {row.dataset_key: row for row in sources}
    return next((by_key[key] for key in keys if key in by_key), None)


def _inputs(context: RequestContext, engine: Engine):
    sources = DataHubRepository(engine).list_active_sources(context.organization_id, context.facility_id)
    inventory_source = _pick(sources, _INVENTORY_KEYS)
    sales_source = _pick(sources, _SALES_KEYS)
    if inventory_source is None or sales_source is None:
        missing = []
        if inventory_source is None: missing.append("Inventory")
        if sales_source is None: missing.append("Product Sales")
        raise HTTPException(
            422,
            f"Buyer Operations needs active {' and '.join(missing)} data in Data & Settings before this workspace can run.",
        )
    try:
        inventory = read_tabular_bytes(inventory_source.payload, inventory_source.filename)
        sales = read_tabular_bytes(sales_source.payload, sales_source.filename)
    except Exception as exc:
        raise HTTPException(422, f"The active Buyer Operations sources could not be read: {exc}") from exc
    return inventory, sales, inventory_source, sales_source


def _model(
    context: RequestContext,
    engine: Engine,
    target_doh: int,
    velocity_adjustment: float,
    sales_days: int,
):
    inventory, sales, inventory_source, sales_source = _inputs(context, engine)
    try:
        detail, product, inv_normalized, sales_normalized = build_forecast(
            inventory,
            sales,
            doh_threshold=target_doh,
            velocity_adjustment=velocity_adjustment,
            sales_period_days=sales_days,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return detail, product, inv_normalized, sales_normalized, inventory_source, sales_source


@router.get("/dashboard")
def dashboard(
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    sku_window: int = Query(56, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    detail, product, _inv, _sales, inventory_source, sales_source = _model(
        context, engine, target_doh, velocity_adjustment, sales_days
    )
    # The old SKU Buyer View rebuilds velocity using its own window.
    _, sku_product, _inv2, _sales2, _, _ = _model(
        context, engine, target_doh, velocity_adjustment, sku_window
    )
    categories = category_dos(detail, product)
    forecast = forecast_view(detail, product)
    sku = sku_inventory_view(sku_product)
    reorder = sku[sku["status"].astype(str).str.contains("Reorder", regex=False)] if not sku.empty else sku
    overstock = sku[sku["status"].astype(str).str.contains("Overstock", regex=False)] if not sku.empty else sku
    expiring = sku[sku["status"].astype(str).str.contains("Expiring", regex=False)] if not sku.empty else sku
    total_units = float(detail["unitssold"].sum()) if "unitssold" in detail else 0.0
    reorder_asap = int((detail.get("reorderpriority") == "1 – Reorder ASAP").sum()) if "reorderpriority" in detail else 0
    return {
        "controls": {
            "target_doh": target_doh,
            "velocity_adjustment": velocity_adjustment,
            "sales_days": sales_days,
            "sku_window": sku_window,
        },
        "summary": {
            "units_sold": total_units,
            "reorder_asap": reorder_asap,
            "tracked_products": int(len(product)),
            "categories": int(detail["subcategory"].nunique()) if "subcategory" in detail else 0,
        },
        "sources": {
            "inventory": {"filename": inventory_source.filename, "rows": inventory_source.row_count, "activated_at": inventory_source.activated_at},
            "sales": {"filename": sales_source.filename, "rows": sales_source.row_count, "activated_at": sales_source.activated_at},
        },
        "category_dos": records(categories),
        "forecast": records(forecast),
        "product_rows": records(product.sort_values("unitssold", ascending=False) if "unitssold" in product else product, limit=PRODUCT_TABLE_DISPLAY_LIMIT),
        "product_rows_total": int(len(product)),
        "sku_views": {
            "all": records(sku),
            "reorder": records(reorder),
            "overstock": records(overstock),
            "expiring": records(expiring),
        },
    }


@router.get("/trends")
def buyer_trends(
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _detail, product, _inv, sales, _inventory_source, _sales_source = _model(
        context, engine, target_doh, velocity_adjustment, sales_days
    )
    output = trends(product, sales)
    return {"sales_days": sales_days, **{name: records(frame, limit=500) for name, frame in output.items()}}


@router.get("/intelligence")
def intelligence(
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _detail, product, _inv, _sales, _inventory_source, _sales_source = _model(
        context, engine, target_doh, velocity_adjustment, sales_days
    )
    result = buyer_intelligence(product)
    return {
        "sales_days": sales_days,
        "summary": result["summary"],
        "purchase_priorities": records(result["purchase_priorities"]),
        "sku_risk": records(result["sku_risk"]),
        "overstock_watch": records(result["overstock_watch"]),
        "category_risk": records(result["category_risk"]),
    }


@router.get("/export")
def export(
    kind: str = Query("forecast", pattern="^(forecast|product|sku)$"),
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    sku_window: int = Query(56, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    detail, product, _inv, _sales, _inventory_source, _sales_source = _model(
        context, engine, target_doh, velocity_adjustment, sales_days if kind != "sku" else sku_window
    )
    if kind == "forecast":
        frame = forecast_view(detail, product)
        filename, sheet = "forecast_table.xlsx", "Forecast"
    elif kind == "product":
        frame = product.sort_values("unitssold", ascending=False).head(PRODUCT_TABLE_DISPLAY_LIMIT) if "unitssold" in product else product.head(PRODUCT_TABLE_DISPLAY_LIMIT)
        filename, sheet = "product_level_forecast.xlsx", "Product Rows"
    else:
        frame = sku_inventory_view(product)
        filename, sheet = "sku_inventory_buyer_view.xlsx", "SKU Buyer View"
    payload = xlsx_bytes(frame, sheet)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
