"""Bounded organization-wide read model for the Enterprise Control Tower.

The control tower ranks every active facility at once. Inventory, commercial
orders, and production orders therefore belong in organization-wide grouped
reads, not one query per facility or one hydrated ORM row per source record.
Keep the projection small and leave the existing traceability, compliance, and
finance services as the source of truth for those domain summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, and_, case, func, select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, InventoryLot, InventoryTransaction, Product, ProductionOrder
from modules.commercial.repository import OPEN_ORDER_STATUSES


def organization_facility_metrics(
    engine: Engine,
    organization_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Return inventory/order/production metrics for every facility in 3 SQL reads."""
    anchor = now or datetime.now(timezone.utc)

    balance = (
        select(
            InventoryTransaction.lot_id.label("lot_id"),
            func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
        )
        .where(InventoryTransaction.organization_id == organization_id)
        .group_by(InventoryTransaction.lot_id)
        .subquery()
    )
    on_hand = func.coalesce(balance.c.balance, 0.0)
    unit_cost = func.coalesce(Product.unit_cost, 0.0)

    with Session(engine) as session:
        inventory_rows = session.execute(
            select(
                InventoryLot.facility_id,
                func.coalesce(
                    func.sum(case((on_hand > 0, 1), else_=0)),
                    0,
                ).label("positive_lots"),
                func.coalesce(
                    func.sum(case((on_hand > 0, on_hand * unit_cost), else_=0.0)),
                    0.0,
                ).label("inventory_value"),
            )
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .outerjoin(
                Product,
                and_(
                    Product.id == InventoryLot.product_id,
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                ),
            )
            .where(InventoryLot.organization_id == organization_id)
            .group_by(InventoryLot.facility_id)
        ).all()

        commercial_rows = session.execute(
            select(
                CommercialOrder.facility_id,
                func.coalesce(
                    func.sum(case((CommercialOrder.order_type == "sales", 1), else_=0)),
                    0,
                ).label("sales"),
                func.coalesce(
                    func.sum(case((CommercialOrder.order_type == "purchase", 1), else_=0)),
                    0,
                ).label("purchase"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                CommercialOrder.due_at.is_not(None)
                                & (CommercialOrder.due_at < anchor),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("overdue"),
            )
            .where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.status.in_(OPEN_ORDER_STATUSES),
            )
            .group_by(CommercialOrder.facility_id)
        ).all()

        production_rows = session.execute(
            select(
                ProductionOrder.facility_id,
                func.count(ProductionOrder.id).label("open"),
                func.coalesce(func.sum(ProductionOrder.requested_units), 0).label("units"),
            )
            .where(
                ProductionOrder.organization_id == organization_id,
                ProductionOrder.status.not_in({"complete", "cancelled"}),
            )
            .group_by(ProductionOrder.facility_id)
        ).all()

    inventory = {
        str(facility_id): {
            "positive_lots": int(positive_lots or 0),
            "value": float(inventory_value or 0.0),
        }
        for facility_id, positive_lots, inventory_value in inventory_rows
    }
    orders = {
        str(facility_id): {
            "sales": int(sales or 0),
            "purchase": int(purchase or 0),
            "overdue": int(overdue or 0),
        }
        for facility_id, sales, purchase, overdue in commercial_rows
    }
    production = {
        str(facility_id): {"open": int(open_count or 0), "units": int(units or 0)}
        for facility_id, open_count, units in production_rows
    }
    return {"inventory": inventory, "orders": orders, "production": production}
