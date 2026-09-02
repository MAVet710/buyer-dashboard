"""Bounded organization-wide read models for the Enterprise Control Tower.

The control tower ranks every active facility at once. Facility-level summary
facts therefore belong in organization-wide grouped reads, not one repository
call per facility or one hydrated ORM row per source record. The projections
below remain read-models over canonical tables and do not create a second
source of truth.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Engine, and_, case, func, select, update
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, InventoryLot, InventoryTransaction, Product, ProductionOrder
from modules.commercial.repository import OPEN_ORDER_STATUSES
from modules.commercial_finance.models import CommercialInvoice
from modules.operational_moats.models import LabelReview, SOPDeviation
from modules.traceability.models import TraceabilityTransaction


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


def organization_secondary_metrics(
    engine: Engine,
    organization_id: str,
    *,
    today: date | None = None,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Return traceability/compliance/A-R summaries in four fixed SELECTs.

    The legacy control-tower path loaded four domain collections separately for
    every facility. This projection preserves the existing summary semantics,
    including the latest-100 label review window and overdue-invoice status
    maintenance, while making query count independent of facility count.
    """
    anchor_date = today or date.today()

    ranked_labels = (
        select(
            LabelReview.facility_id.label("facility_id"),
            LabelReview.status.label("status"),
            func.row_number()
            .over(
                partition_by=LabelReview.facility_id,
                order_by=LabelReview.reviewed_at.desc(),
            )
            .label("row_number"),
        )
        .where(LabelReview.organization_id == organization_id)
        .subquery()
    )

    with Session(engine) as session:
        trace_rows = session.execute(
            select(
                TraceabilityTransaction.facility_id,
                TraceabilityTransaction.status,
                func.count(TraceabilityTransaction.id),
            )
            .where(TraceabilityTransaction.organization_id == organization_id)
            .group_by(TraceabilityTransaction.facility_id, TraceabilityTransaction.status)
        ).all()

        deviation_rows = session.execute(
            select(
                SOPDeviation.facility_id,
                func.count(SOPDeviation.id).label("open_count"),
                func.coalesce(
                    func.sum(case((SOPDeviation.severity == "critical", 1), else_=0)),
                    0,
                ).label("critical_count"),
                func.coalesce(
                    func.sum(case((SOPDeviation.severity == "high", 1), else_=0)),
                    0,
                ).label("high_count"),
            )
            .where(
                SOPDeviation.organization_id == organization_id,
                SOPDeviation.status.in_(("open", "investigating")),
            )
            .group_by(SOPDeviation.facility_id)
        ).all()

        label_rows = session.execute(
            select(
                ranked_labels.c.facility_id,
                func.coalesce(
                    func.sum(case((ranked_labels.c.status == "fail", 1), else_=0)),
                    0,
                ).label("failures"),
            )
            .where(ranked_labels.c.row_number <= 100)
            .group_by(ranked_labels.c.facility_id)
        ).all()

        session.execute(
            update(CommercialInvoice)
            .where(
                CommercialInvoice.organization_id == organization_id,
                CommercialInvoice.status.in_(("sent", "partial")),
                CommercialInvoice.due_date < anchor_date,
            )
            .values(status="overdue")
        )
        finance_rows = session.execute(
            select(
                CommercialInvoice.facility_id,
                func.coalesce(func.sum(CommercialInvoice.balance_usd), 0.0).label("total_ar"),
            )
            .where(
                CommercialInvoice.organization_id == organization_id,
                CommercialInvoice.status.not_in(("paid", "void")),
            )
            .group_by(CommercialInvoice.facility_id)
        ).all()
        session.commit()

    traceability: dict[str, dict[str, int]] = {}
    for facility_id, status, count in trace_rows:
        row = traceability.setdefault(str(facility_id), {})
        row[str(status)] = int(count or 0)
    for row in traceability.values():
        row["total"] = sum(
            value for key, value in row.items() if key not in {"total", "needs_reconciliation", "in_flight"}
        )
        row["needs_reconciliation"] = int(row.get("rejected", 0)) + int(
            row.get("reconciliation_required", 0)
        )
        row["in_flight"] = sum(
            int(row.get(status, 0))
            for status in ("requested", "validated", "queued", "submitted", "accepted")
        )

    compliance = {
        str(facility_id): {
            "open_sop_deviations": int(open_count or 0),
            "critical_sop": int(critical_count or 0),
            "high_sop": int(high_count or 0),
            "label_failures": 0,
        }
        for facility_id, open_count, critical_count, high_count in deviation_rows
    }
    for facility_id, failures in label_rows:
        compliance.setdefault(
            str(facility_id),
            {
                "open_sop_deviations": 0,
                "critical_sop": 0,
                "high_sop": 0,
                "label_failures": 0,
            },
        )["label_failures"] = int(failures or 0)

    finance = {
        str(facility_id): {"ar": float(total_ar or 0.0)}
        for facility_id, total_ar in finance_rows
    }
    return {"traceability": traceability, "compliance": compliance, "finance": finance}
