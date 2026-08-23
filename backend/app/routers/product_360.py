from __future__ import annotations

import json
import math
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    ProductionOrder,
    RetailSale,
    utc_now,
)
from modules.product_master import ProductMasterRepository
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/product-360", tags=["product-360"])
TARGET_DAYS = 21


def _metadata(notes: str) -> dict:
    try:
        value = json.loads(notes or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _snapshot(product_id: str, context: RequestContext, engine: Engine) -> dict:
    try:
        master = ProductMasterRepository(engine).snapshot(context.organization_id, product_id, history_limit=20)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    product = master["product"]
    profile = master["profile"]
    now = utc_now()

    with Session(engine) as session:
        balance_rows = list(
            session.execute(
                select(
                    InventoryLot,
                    func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0),
                )
                .outerjoin(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id)
                .where(
                    InventoryLot.organization_id == context.organization_id,
                    InventoryLot.facility_id == context.facility_id,
                    InventoryLot.product_id == product_id,
                )
                .group_by(InventoryLot.id)
                .order_by(InventoryLot.received_at.desc().nullslast())
            )
        )
        lot_ids = [lot.id for lot, _ in balance_rows]
        reserved_by_lot: dict[str, float] = {}
        if lot_ids:
            reserved_by_lot = {
                str(lot_id): float(quantity or 0.0)
                for lot_id, quantity in session.execute(
                    select(
                        MaterialReservation.lot_id,
                        func.coalesce(func.sum(MaterialReservation.quantity), 0.0),
                    )
                    .where(
                        MaterialReservation.organization_id == context.organization_id,
                        MaterialReservation.facility_id == context.facility_id,
                        MaterialReservation.lot_id.in_(lot_ids),
                        MaterialReservation.status == "reserved",
                    )
                    .group_by(MaterialReservation.lot_id)
                )
            }

        sales_windows: dict[int, dict[str, float]] = {}
        for days in (7, 30, 60, 90):
            quantity, net_sales = session.execute(
                select(
                    func.coalesce(func.sum(RetailSale.quantity), 0.0),
                    func.coalesce(func.sum(RetailSale.net_sales), 0.0),
                ).where(
                    RetailSale.organization_id == context.organization_id,
                    RetailSale.facility_id == context.facility_id,
                    RetailSale.product_id == product_id,
                    RetailSale.sold_at >= now - timedelta(days=days),
                    RetailSale.sold_at <= now,
                )
            ).one()
            sales_windows[days] = {"quantity": float(quantity or 0.0), "net_sales": float(net_sales or 0.0)}

        order_lines = list(
            session.execute(
                select(CommercialOrderLine, CommercialOrder)
                .join(CommercialOrder, CommercialOrder.id == CommercialOrderLine.commercial_order_id)
                .where(
                    CommercialOrderLine.organization_id == context.organization_id,
                    CommercialOrderLine.product_id == product_id,
                    CommercialOrder.facility_id == context.facility_id,
                    CommercialOrder.status.not_in(["fulfilled", "cancelled"]),
                )
                .order_by(CommercialOrder.created_at.desc())
                .limit(20)
            )
        )
        production = list(
            session.scalars(
                select(ProductionOrder)
                .where(
                    ProductionOrder.organization_id == context.organization_id,
                    ProductionOrder.facility_id == context.facility_id,
                    ((ProductionOrder.sku == product.sku) | (ProductionOrder.product_name == product.name)),
                )
                .order_by(ProductionOrder.created_at.desc())
                .limit(20)
            )
        )

    packages = []
    for lot, balance in balance_rows:
        meta = _metadata(lot.notes)
        packages.append(
            {
                "id": lot.id,
                "package_id": lot.compliance_package_id or lot.lot_code,
                "lot_code": lot.lot_code,
                "location": lot.location_code,
                "status": lot.status,
                "balance": float(balance or 0.0),
                "reserved": reserved_by_lot.get(str(lot.id), 0.0),
                "unit": product.base_unit,
                "received_at": lot.received_at,
                "expiration_at": lot.expiration_at,
                "lab_status": str(meta.get("lab_testing_state") or ""),
                "coa_reference": str(meta.get("coa_reference") or ""),
                "source_name": str(meta.get("source_name") or ""),
            }
        )

    on_hand = sum(row["balance"] for row in packages)
    reserved = sum(row["reserved"] for row in packages)
    available_after_reserved = max(0.0, on_hand - reserved)
    sold_30d = sales_windows[30]["quantity"]
    daily_velocity = sold_30d / 30.0 if sold_30d > 0 else 0.0
    days_on_hand = on_hand / daily_velocity if daily_velocity > 0 else None
    target_units = max(0, math.ceil(daily_velocity * TARGET_DAYS - on_hand)) if daily_velocity > 0 else 0
    unit_cost = max(0.0, float(product.unit_cost or 0.0))
    retail_price = max(0.0, float(product.retail_price or 0.0))
    margin_pct = ((retail_price - unit_cost) / retail_price * 100.0) if retail_price > 0 else None
    inventory_value = max(0.0, on_hand) * unit_cost
    retail_value = max(0.0, on_hand) * retail_price
    gross_profit_value = max(0.0, on_hand) * max(0.0, retail_price - unit_cost)
    reorder_cost = target_units * unit_cost
    reorder_retail_value = target_units * retail_price
    reorder_gross_profit = target_units * max(0.0, retail_price - unit_cost)
    sell_through_denominator = sold_30d + on_hand
    sell_through_pct = sold_30d / sell_through_denominator * 100.0 if sell_through_denominator > 0 else 0.0
    pace_7 = sales_windows[7]["quantity"] / 7.0
    pace_30 = sales_windows[30]["quantity"] / 30.0
    sales_trend_pct = ((pace_7 / pace_30) - 1.0) * 100.0 if pace_30 > 0 else None
    stockout_date = None
    if days_on_hand is not None and days_on_hand >= 0:
        stockout_date = (now + timedelta(days=max(0, math.ceil(days_on_hand)))).date().isoformat()

    received_dates = [row["received_at"] for row in packages if row["received_at"] is not None]
    expiration_dates = [row["expiration_at"] for row in packages if row["expiration_at"] is not None]
    oldest_age_days = None
    last_received_date = None
    nearest_expiration_days = None
    if received_dates:
        normalized = [value if value.tzinfo is not None else value.replace(tzinfo=now.tzinfo) for value in received_dates]
        oldest_age_days = max(0, int((now - min(normalized)).total_seconds() // 86400))
        last_received_date = max(normalized).date().isoformat()
    if expiration_dates:
        normalized_expirations = [value if value.tzinfo is not None else value.replace(tzinfo=now.tzinfo) for value in expiration_dates]
        nearest_expiration_days = int((min(normalized_expirations) - now).total_seconds() // 86400)

    if daily_velocity <= 0 and on_hand > 0:
        decision_signal = "SELL-THROUGH REVIEW"
        decision_reason = "Inventory is on hand but no recent unit velocity is visible."
    elif target_units > 0 and days_on_hand is not None and days_on_hand <= 7:
        decision_signal = "ORDER NOW"
        decision_reason = f"Coverage is {days_on_hand:.1f} days; {target_units:,} units are needed to reach the {TARGET_DAYS}-day target."
    elif target_units > 0:
        decision_signal = "REORDER"
        decision_reason = f"Current normalized velocity supports a {target_units:,}-unit draft reorder to reach {TARGET_DAYS} days of supply."
    else:
        decision_signal = "HEALTHY"
        decision_reason = f"No immediate {TARGET_DAYS}-day replenishment gap is visible."

    status = next((row["status"] for row in packages if row["status"]), "")
    lab_status = next((row["lab_status"] for row in packages if row["lab_status"]), "")

    return {
        "product": {
            key: getattr(product, key)
            for key in ("id", "sku", "name", "item_type", "base_unit", "unit_cost", "retail_price", "upc", "active")
        },
        "profile": {
            key: getattr(profile, key)
            for key in ("brand", "category", "subcategory", "strain", "manufacturer", "product_format", "description", "retail_enabled", "production_enabled")
        } if profile else None,
        "inventory": {
            "packages": packages,
            "on_hand": on_hand,
            "reserved": reserved,
            "available_after_reserved": available_after_reserved,
            "package_count": len(packages),
        },
        "sales": {
            "windows": {str(days): values for days, values in sales_windows.items()},
            "daily_velocity": daily_velocity,
            "sales_trend_pct": sales_trend_pct,
            "source": "Durable facility retail sales trailing windows",
        },
        "decision": {
            "signal": decision_signal,
            "reason": decision_reason,
            "target_days": TARGET_DAYS,
            "target_units": target_units,
            "days_on_hand": days_on_hand,
            "stockout_date": stockout_date,
        },
        "economics": {
            "unit_cost": unit_cost,
            "retail_price": retail_price,
            "margin_pct": margin_pct,
            "inventory_value": inventory_value,
            "retail_value": retail_value,
            "gross_profit_value": gross_profit_value,
            "sell_through_pct": sell_through_pct,
            "estimated_reorder_cost": reorder_cost,
            "estimated_reorder_retail_value": reorder_retail_value,
            "estimated_reorder_gross_profit": reorder_gross_profit,
        },
        "age": {
            "oldest_age_days": oldest_age_days,
            "nearest_expiration_days": nearest_expiration_days,
            "last_received_date": last_received_date,
        },
        "compliance": {"status": status, "lab_status": lab_status},
        "open_orders": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "order_type": order.order_type,
                "status": order.status,
                "quantity": float(line.quantity),
                "fulfilled_quantity": float(line.fulfilled_quantity),
                "unit": line.unit,
            }
            for line, order in order_lines
        ],
        "production_orders": [
            {key: getattr(row, key) for key in ("id", "order_number", "status", "requested_units", "due_at", "product_format")}
            for row in production
        ],
        "aliases": [{"alias": row.alias, "source": row.source} for row in master["aliases"]],
        "mappings": [{"system_name": row.system_name, "external_id": row.external_id, "external_name": row.external_name} for row in master["mappings"]],
        "value_history": [{"value_type": row.value_type, "amount": row.amount, "currency": row.currency, "effective_at": row.effective_at} for row in master["value_history"]],
    }


@router.get("/by-lot/{lot_id}")
def product_360_by_lot(
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    with Session(engine) as session:
        lot = session.get(InventoryLot, lot_id)
        if not lot or lot.organization_id != context.organization_id or lot.facility_id != context.facility_id:
            raise HTTPException(404, "Inventory lot was not found in the active facility.")
        product_id = lot.product_id
    return _snapshot(product_id, context, engine)


@router.get("/{product_id}")
def product_360(
    product_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    return _snapshot(product_id, context, engine)
