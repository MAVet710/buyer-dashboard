"""Cross-ledger profitability intelligence without creating a parallel accounting ledger."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine, Product, RetailSale
from modules.production_erp.models import ProductionCostEvent, ProductionRunOutput


def profitability_360(engine: Engine, organization_id: str, facility_id: str) -> dict[str, Any]:
    """Return product profitability grounded in canonical retail/commercial/production records.

    Wholesale revenue is recognized only for fulfilled units. Open sales-order demand is
    useful planning context, but it is not realized revenue and must not inflate margin.
    """
    with Session(engine) as session:
        products = {
            row.id: row
            for row in session.scalars(
                select(Product).where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                )
            )
        }
        retail_sales = list(
            session.scalars(
                select(RetailSale).where(
                    RetailSale.organization_id == organization_id,
                    RetailSale.facility_id == facility_id,
                )
            )
        )
        sales_orders = {
            row.id: row
            for row in session.scalars(
                select(CommercialOrder).where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.facility_id == facility_id,
                    CommercialOrder.order_type == "sales",
                    CommercialOrder.status != "cancelled",
                )
            )
        }
        order_lines = list(
            session.scalars(
                select(CommercialOrderLine).where(
                    CommercialOrderLine.organization_id == organization_id,
                    CommercialOrderLine.commercial_order_id.in_(tuple(sales_orders) or ("",)),
                    CommercialOrderLine.fulfilled_quantity > 0,
                )
            )
        )
        outputs = list(
            session.scalars(
                select(ProductionRunOutput).where(
                    ProductionRunOutput.organization_id == organization_id,
                    ProductionRunOutput.facility_id == facility_id,
                    ProductionRunOutput.actual_quantity > 0,
                )
            )
        )
        output_order_ids = {row.production_order_id for row in outputs}
        costs = list(
            session.scalars(
                select(ProductionCostEvent).where(
                    ProductionCostEvent.organization_id == organization_id,
                    ProductionCostEvent.facility_id == facility_id,
                    ProductionCostEvent.production_order_id.in_(tuple(output_order_ids) or ("",)),
                )
            )
        )

    stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "retail_units": 0.0,
            "retail_revenue": 0.0,
            "wholesale_units": 0.0,
            "wholesale_revenue": 0.0,
            "standard_cogs": 0.0,
            "production_allocated_cost": 0.0,
            "production_output_units": 0.0,
        }
    )
    for sale in retail_sales:
        if not sale.product_id or sale.product_id not in products:
            continue
        bucket = stats[sale.product_id]
        quantity = float(sale.quantity or 0)
        bucket["retail_units"] += quantity
        bucket["retail_revenue"] += float(sale.net_sales or 0)
        bucket["standard_cogs"] += max(0.0, quantity) * float(products[sale.product_id].unit_cost or 0)

    for line in order_lines:
        if line.product_id not in products:
            continue
        quantity = float(line.fulfilled_quantity or 0)
        if quantity <= 0:
            continue
        bucket = stats[line.product_id]
        bucket["wholesale_units"] += quantity
        bucket["wholesale_revenue"] += quantity * float(line.unit_price or 0)
        bucket["standard_cogs"] += quantity * float(products[line.product_id].unit_cost or 0)

    costs_by_order: dict[str, float] = defaultdict(float)
    for cost in costs:
        costs_by_order[cost.production_order_id] += float(cost.amount_usd or 0)

    outputs_by_order: dict[str, list[ProductionRunOutput]] = defaultdict(list)
    for output in outputs:
        outputs_by_order[output.production_order_id].append(output)

    for order_id, order_outputs in outputs_by_order.items():
        total_quantity = sum(float(row.actual_quantity or 0) for row in order_outputs)
        total_cost = costs_by_order.get(order_id, 0.0)
        for output in order_outputs:
            quantity = float(output.actual_quantity or 0)
            share = quantity / total_quantity if total_quantity > 0 else 0.0
            bucket = stats[output.product_id]
            bucket["production_output_units"] += quantity
            bucket["production_allocated_cost"] += total_cost * share

    rows = []
    for product_id, product in products.items():
        bucket = stats.get(product_id)
        if not bucket:
            continue
        revenue = bucket["retail_revenue"] + bucket["wholesale_revenue"]
        standard_cogs = bucket["standard_cogs"]
        gross_profit = revenue - standard_cogs
        rows.append(
            {
                "product_id": product_id,
                "sku": product.sku,
                "product_name": product.name,
                **bucket,
                "revenue": revenue,
                "gross_profit": gross_profit,
                "gross_margin_pct": gross_profit / revenue * 100.0 if revenue else 0.0,
                "actual_production_cost_per_unit": (
                    bucket["production_allocated_cost"] / bucket["production_output_units"]
                    if bucket["production_output_units"]
                    else 0.0
                ),
            }
        )

    rows.sort(key=lambda item: item["revenue"], reverse=True)
    total_revenue = sum(row["revenue"] for row in rows)
    total_cogs = sum(row["standard_cogs"] for row in rows)
    return {
        "summary": {
            "revenue": total_revenue,
            "standard_cogs": total_cogs,
            "gross_profit": total_revenue - total_cogs,
            "gross_margin_pct": ((total_revenue - total_cogs) / total_revenue * 100.0) if total_revenue else 0.0,
            "tracked_products": len(rows),
        },
        "products": rows,
    }
