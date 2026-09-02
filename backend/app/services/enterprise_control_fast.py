"""Bounded organization-wide read model for the Enterprise Control Tower.

The control tower ranks every active facility at once. Inventory, commercial
orders, and production orders therefore belong in organization-wide reads,
not one query per facility. Keep the projection small and leave the existing
traceability, compliance, and finance services as the source of truth for
those domain summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, and_, func, select
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
    inventory: dict[str, dict[str, float | int]] = {}
    orders: dict[str, dict[str, float | int]] = {}
    production: dict[str, dict[str, float | int]] = {}

    balance = (
        select(
            InventoryTransaction.lot_id.label("lot_id"),
            func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
        )
        .where(InventoryTransaction.organization_id == organization_id)
        .group_by(InventoryTransaction.lot_id)
        .subquery()
    )

    with Session(engine) as session:
        inventory_rows = session.execute(
            select(
                InventoryLot.facility_id,
                func.coalesce(balance.c.balance, 0.0),
                func.coalesce(Product.unit_cost, 0.0),
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
        ).all()

        commercial_rows = list(
            session.scalars(
                select(CommercialOrder).where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.status.in_(OPEN_ORDER_STATUSES),
                )
            )
        )

        production_rows = list(
            session.scalars(
                select(ProductionOrder).where(
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.status.not_in({"complete", "cancelled"}),
                )
            )
        )

    for facility_id, raw_balance, raw_unit_cost in inventory_rows:
        value = float(raw_balance or 0.0)
        row = inventory.setdefault(str(facility_id), {"positive_lots": 0, "value": 0.0})
        if value > 0:
            row["positive_lots"] = int(row["positive_lots"]) + 1
            row["value"] = float(row["value"]) + value * float(raw_unit_cost or 0.0)

    for record in commercial_rows:
        row = orders.setdefault(record.facility_id, {"sales": 0, "purchase": 0, "overdue": 0})
        if record.order_type == "sales":
            row["sales"] = int(row["sales"]) + 1
        elif record.order_type == "purchase":
            row["purchase"] = int(row["purchase"]) + 1
        if record.due_at:
            due_at = record.due_at if record.due_at.tzinfo else record.due_at.replace(tzinfo=timezone.utc)
            if due_at < anchor:
                row["overdue"] = int(row["overdue"]) + 1

    for record in production_rows:
        row = production.setdefault(record.facility_id, {"open": 0, "units": 0})
        row["open"] = int(row["open"]) + 1
        row["units"] = int(row["units"]) + int(record.requested_units or 0)

    return {"inventory": inventory, "orders": orders, "production": production}
