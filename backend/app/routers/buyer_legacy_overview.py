from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine

from services.web_buyer_parity import records, sku_inventory_view
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine
from .buyer_parity import _model

router = APIRouter(
    prefix="/buyer-parity",
    tags=["buyer-parity"],
    dependencies=[Depends(get_retail_context)],
)


def _date_column(frame: pd.DataFrame) -> str | None:
    # Buyer uploads frequently carry a transaction timestamp as "Order Time"
    # rather than a field literally containing "date". The previous detector
    # therefore produced healthy KPI totals but an empty Sales Trend chart.
    preferred = [
        "date",
        "sold_at",
        "sale_date",
        "sale_time",
        "order_date",
        "order_time",
        "transaction_date",
        "transaction_time",
        "timestamp",
        "datetime",
        "created_at",
        "day",
    ]
    by_normalized = {
        str(column).strip().casefold().replace(" ", "_"): column
        for column in frame.columns
    }
    for key in preferred:
        if key in by_normalized:
            return str(by_normalized[key])
    return next(
        (
            str(column)
            for column in frame.columns
            if any(token in str(column).casefold() for token in ("date", "time", "timestamp"))
        ),
        None,
    )


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(0.0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


@router.get("/legacy-overview")
def legacy_overview(
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    sku_window: int = Query(56, ge=7, le=120),
    top_n: int = Query(10, ge=1, le=50),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _detail, product, inv_normalized, sales_normalized, _inventory_source, _sales_source = _model(
        context,
        engine,
        target_doh,
        velocity_adjustment,
        sales_days,
    )
    sku = sku_inventory_view(inv_normalized, sales_normalized, sku_window)

    sales = sales_normalized.copy()
    if "unitssold" in sales:
        sales["unitssold"] = pd.to_numeric(sales["unitssold"], errors="coerce").fillna(0)
    if "net_sales" in sales:
        sales["net_sales"] = pd.to_numeric(sales["net_sales"], errors="coerce").fillna(0)

    daily = pd.DataFrame(columns=["date", "units", "revenue"])
    date_column = _date_column(sales)
    if date_column and date_column in sales:
        dated = sales.copy()
        dated[date_column] = pd.to_datetime(dated[date_column], errors="coerce")
        dated = dated[dated[date_column].notna()].copy()
        if not dated.empty:
            dated["date"] = dated[date_column].dt.date.astype(str)
            aggregate = {"unitssold": "sum"}
            if "net_sales" in dated:
                aggregate["net_sales"] = "sum"
            daily = dated.groupby("date", as_index=False).agg(aggregate).rename(
                columns={"unitssold": "units", "net_sales": "revenue"}
            )
            if "revenue" not in daily:
                daily["revenue"] = 0.0
            daily = daily.sort_values("date")

    category_revenue = pd.DataFrame(columns=["category", "units", "revenue"])
    if "mastercategory" in sales:
        aggregate = {"unitssold": "sum"}
        if "net_sales" in sales:
            aggregate["net_sales"] = "sum"
        category_revenue = sales.groupby("mastercategory", dropna=False, as_index=False).agg(aggregate).rename(
            columns={"mastercategory": "category", "unitssold": "units", "net_sales": "revenue"}
        )
        if "revenue" not in category_revenue:
            category_revenue["revenue"] = 0.0
        category_revenue = category_revenue.sort_values(["revenue", "units"], ascending=False)

    product_health = product.copy()
    on_hand = _numeric(product_health, "onhandunits")
    sold = _numeric(product_health, "unitssold")
    velocity = _numeric(product_health, "avgunitsperday")
    doh = _numeric(product_health, "daysonhand")
    reorder_skus = int(((doh < target_doh) & (velocity > 0)).sum())
    at_risk = int(((doh > 0) & (doh <= 7) & (velocity > 0)).sum())
    slow_movers = int(((velocity <= 0) & (on_hand > 0)).sum())
    overstock = int(((doh >= 60) & (on_hand > 0)).sum())
    health_score = max(0, min(100, int(100 - reorder_skus * 2 - at_risk * 3 - slow_movers)))

    sku_work = sku.copy()
    dollars = _numeric(sku_work, "dollars_on_hand")
    days_supply = _numeric(sku_work, "days_of_supply")
    on_hand_sku = _numeric(sku_work, "onhandunits")
    weekly = _numeric(sku_work, "avg_weekly_sales")
    sku_work["_slow_rank"] = np.where(weekly <= 0, 10000, days_supply)
    sku_work["_inventory_value"] = dollars
    slow = sku_work[on_hand_sku > 0].sort_values(
        ["_slow_rank", "_inventory_value"], ascending=False
    ).head(top_n).copy()
    slow = slow.drop(
        columns=[column for column in ["_slow_rank", "_inventory_value"] if column in slow],
        errors="ignore",
    )

    expiring_mask = pd.Series(False, index=sku_work.index)
    if "days_to_expire" in sku_work:
        days_to_expire = pd.to_numeric(sku_work["days_to_expire"], errors="coerce")
        expiring_mask = days_to_expire.notna() & (days_to_expire < 60) & (days_to_expire >= 0)
    overstock_mask = days_supply >= 90
    reorder_mask = (days_supply > 0) & (days_supply <= 21)
    no_stock_mask = on_hand_sku <= 0

    return {
        "sales_trend": records(daily),
        "revenue_by_category": records(category_revenue),
        "top_slow_movers": records(slow),
        "inventory_health": {
            "score": health_score,
            "reorder_skus": reorder_skus,
            "at_risk_skus": at_risk,
            "slow_movers": slow_movers,
            "overstock_skus": overstock,
        },
        "inventory_condition": {
            "reorder_count": int(reorder_mask.sum()),
            "overstock_count": int(overstock_mask.sum()),
            "expiring_count": int(expiring_mask.sum()),
            "no_stock_count": int(no_stock_mask.sum()),
            "overstock_cost_exposure": float(dollars[overstock_mask].sum()),
            "expiring_cost_exposure": float(dollars[expiring_mask].sum()),
            "on_hand_cost": float(dollars.sum()),
            "units_on_hand": float(on_hand_sku.sum()),
            "units_sold": float(sold.sum()),
        },
    }
