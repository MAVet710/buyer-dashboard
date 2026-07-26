"""Presentation-ready commercial order metrics with no UI dependencies."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable


OPEN_STATUSES = {"draft", "confirmed", "allocated", "partially_fulfilled"}


def order_value_by_id(lines: Iterable[Any]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for line in lines:
        totals[str(line.commercial_order_id)] += float(line.quantity) * float(
            line.unit_price
        )
    return dict(totals)


def fulfillment_by_order(lines: Iterable[Any]) -> dict[str, tuple[float, float]]:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for line in lines:
        values = totals[str(line.commercial_order_id)]
        values[0] += float(line.quantity)
        values[1] += float(line.fulfilled_quantity)
    return {key: (values[0], values[1]) for key, values in totals.items()}


def commercial_dashboard_metrics(
    orders: Iterable[Any],
    lines: Iterable[Any],
    *,
    inventory_value: float = 0.0,
    today: date | None = None,
) -> dict[str, float | int]:
    order_rows = list(orders)
    line_rows = list(lines)
    values = order_value_by_id(line_rows)
    fulfillment = fulfillment_by_order(line_rows)
    current_day = today or date.today()

    open_orders = [order for order in order_rows if order.status in OPEN_STATUSES]
    open_sales_value = sum(
        values.get(str(order.id), 0.0)
        for order in open_orders
        if order.order_type == "sales"
    )
    open_purchase_value = sum(
        values.get(str(order.id), 0.0)
        for order in open_orders
        if order.order_type == "purchase"
    )
    ordered_units = sum(pair[0] for pair in fulfillment.values())
    fulfilled_units = sum(pair[1] for pair in fulfillment.values())
    overdue_orders = 0
    for order in open_orders:
        due_at = getattr(order, "due_at", None)
        due_date = (
            due_at.date()
            if isinstance(due_at, datetime)
            else due_at
            if isinstance(due_at, date)
            else None
        )
        if due_date and due_date < current_day:
            overdue_orders += 1

    return {
        "inventory_value": max(0.0, float(inventory_value)),
        "open_sales_value": open_sales_value,
        "open_purchase_value": open_purchase_value,
        "open_orders": len(open_orders),
        "overdue_orders": overdue_orders,
        "fill_rate_pct": (
            fulfilled_units / ordered_units * 100.0 if ordered_units else 0.0
        ),
    }


def order_status_label(status: str) -> str:
    return str(status or "draft").replace("_", " ").title()
