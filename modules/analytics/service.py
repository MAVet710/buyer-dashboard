"""Profitability analytics aggregating margin data across the entire supply chain."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.db import create_coman_engine
from modules.coman.models import CommercialOrder, CommercialOrderLine, InventoryLot, Product
from modules.commercial_finance.models import CommercialInvoice, CommercialInvoiceLine
from modules.extraction.models import ExtractionRun, ExtractionCostEvent
from modules.production_erp.models import ProductionCostEvent


class ProfitabilityAnalyticsService:
    """Aggregate profitability and margin data across cultivation, processing, extraction, and retail."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def supply_chain_margin(self, organization_id: str, facility_id: str, days_back: int = 30) -> dict[str, Any]:
        """
        Analyze margin at each stage of the supply chain.

        Returns:
            {
                "period_days": int,
                "period_end": date,
                "total_revenue": float,
                "total_cogs": float,
                "gross_margin_pct": float,
                "stage_breakdown": [
                    {
                        "stage": "cultivation",
                        "cost": float,
                        "output_units": float,
                        "cost_per_unit": float,
                    },
                    ...
                ]
            }
        """
        period_end = datetime.now(tz=timezone.utc).date()
        period_start = period_end - timedelta(days=days_back)

        with self._sessions() as session:
            # Revenue from completed sales orders → invoiced
            revenue_stmt = (
                select(func.sum(CommercialInvoiceLine.quantity * CommercialInvoiceLine.unit_price_usd))
                .select_from(CommercialInvoiceLine)
                .join(CommercialInvoice)
                .where(
                    CommercialInvoice.organization_id == organization_id,
                    CommercialInvoice.facility_id == facility_id,
                    CommercialInvoice.issue_date >= period_start,
                    CommercialInvoice.issue_date <= period_end,
                )
            )
            total_revenue = float(session.scalar(revenue_stmt) or 0)

            # COGS from production events (material + labor + overhead)
            cogs_stmt = (
                select(func.sum(ProductionCostEvent.amount_usd))
                .select_from(ProductionCostEvent)
                .where(
                    ProductionCostEvent.organization_id == organization_id,
                    ProductionCostEvent.facility_id == facility_id,
                    ProductionCostEvent.category.in_(["material", "labor", "overhead", "packaging"]),
                    ProductionCostEvent.occurred_at >= period_start,
                    ProductionCostEvent.occurred_at <= period_end,
                )
            )
            production_cogs = float(session.scalar(cogs_stmt) or 0)

            # Extraction COGS (material + labor costs)
            extraction_cogs_stmt = (
                select(func.sum(ExtractionCostEvent.amount_usd))
                .select_from(ExtractionCostEvent)
                .join(ExtractionRun)
                .where(
                    ExtractionCostEvent.organization_id == organization_id,
                    ExtractionCostEvent.facility_id == facility_id,
                    ExtractionCostEvent.category.in_(["material", "labor"]),
                    ExtractionRun.completed_at >= period_start,
                    ExtractionRun.completed_at <= period_end,
                    ExtractionCostEvent.run_id == ExtractionRun.id,
                )
            )
            extraction_cogs = float(session.scalar(extraction_cogs_stmt) or 0)

            total_cogs = production_cogs + extraction_cogs
            gross_margin = total_revenue - total_cogs
            gross_margin_pct = (gross_margin / total_revenue * 100) if total_revenue > 0 else 0

            return {
                "period_days": days_back,
                "period_end": period_end,
                "total_revenue": round(total_revenue, 2),
                "total_cogs": round(total_cogs, 2),
                "gross_margin": round(gross_margin, 2),
                "gross_margin_pct": round(gross_margin_pct, 1),
            }

    def product_profitability(self, organization_id: str, facility_id: str, days_back: int = 30) -> list[dict[str, Any]]:
        """
        Analyze profitability by product SKU.

        Returns list of:
            {
                "product_id": str,
                "product_name": str,
                "sku": str,
                "units_sold": float,
                "revenue": float,
                "cogs": float,
                "margin": float,
                "margin_pct": float,
            }
        """
        period_end = datetime.now(tz=timezone.utc).date()
        period_start = period_end - timedelta(days=days_back)

        with self._sessions() as session:
            # Sales by product
            sales_stmt = (
                select(
                    CommercialOrderLine.product_id,
                    Product.name,
                    Product.sku,
                    func.sum(CommercialOrderLine.quantity).label("units_sold"),
                    func.sum(CommercialOrderLine.quantity * CommercialOrderLine.unit_price).label("revenue"),
                )
                .select_from(CommercialOrderLine)
                .join(Product)
                .join(CommercialOrder)
                .join(CommercialInvoice)
                .where(
                    CommercialOrder.organization_id == organization_id,
                    CommercialOrder.facility_id == facility_id,
                    CommercialInvoice.issue_date >= period_start,
                    CommercialInvoice.issue_date <= period_end,
                )
                .group_by(CommercialOrderLine.product_id, Product.name, Product.sku)
            )

            results = []
            for row in session.execute(sales_stmt).fetchall():
                product_id, product_name, sku, units_sold, revenue = row
                revenue = float(revenue or 0)
                units_sold = float(units_sold or 0)

                # COGS for this product (simplified: avg cost per unit from latest inventory)
                lot_stmt = (
                    select(func.avg(InventoryLot.unit_cost))
                    .where(
                        InventoryLot.organization_id == organization_id,
                        InventoryLot.facility_id == facility_id,
                        InventoryLot.product_id == product_id,
                    )
                )
                avg_unit_cost = float(session.scalar(lot_stmt) or 0)
                cogs = units_sold * avg_unit_cost
                margin = revenue - cogs
                margin_pct = (margin / revenue * 100) if revenue > 0 else 0

                results.append({
                    "product_id": str(product_id),
                    "product_name": str(product_name or "—"),
                    "sku": str(sku or "—"),
                    "units_sold": round(units_sold, 2),
                    "revenue": round(revenue, 2),
                    "cogs": round(cogs, 2),
                    "margin": round(margin, 2),
                    "margin_pct": round(margin_pct, 1),
                })

            return sorted(results, key=lambda x: x["margin"], reverse=True)

    def production_cost_analysis(self, organization_id: str, facility_id: str, days_back: int = 30) -> dict[str, Any]:
        """
        Analyze production costs by category (material, labor, overhead, packaging, waste).
        """
        period_end = datetime.now(tz=timezone.utc).date()
        period_start = period_end - timedelta(days=days_back)

        with self._sessions() as session:
            cost_stmt = (
                select(
                    ProductionCostEvent.category,
                    func.sum(ProductionCostEvent.amount_usd).label("total"),
                    func.count(ProductionCostEvent.id).label("count"),
                )
                .where(
                    ProductionCostEvent.organization_id == organization_id,
                    ProductionCostEvent.facility_id == facility_id,
                    ProductionCostEvent.occurred_at >= period_start,
                    ProductionCostEvent.occurred_at <= period_end,
                )
                .group_by(ProductionCostEvent.category)
            )

            breakdown = {}
            total = 0.0
            for category, amount, count in session.execute(cost_stmt).fetchall():
                amount = float(amount or 0)
                breakdown[str(category)] = {
                    "total_usd": round(amount, 2),
                    "events": int(count or 0),
                }
                total += amount

            return {
                "period_days": days_back,
                "period_end": period_end,
                "total_production_cost": round(total, 2),
                "breakdown": breakdown,
            }

    def extraction_efficiency(self, organization_id: str, facility_id: str, days_back: int = 30) -> dict[str, Any]:
        """
        Analyze extraction yield efficiency and cost per output unit.
        """
        period_end = datetime.now(tz=timezone.utc).date()
        period_start = period_end - timedelta(days=days_back)

        with self._sessions() as session:
            runs_stmt = (
                select(ExtractionRun)
                .where(
                    ExtractionRun.organization_id == organization_id,
                    ExtractionRun.facility_id == facility_id,
                    ExtractionRun.completed_at >= period_start,
                    ExtractionRun.completed_at <= period_end,
                )
            )

            runs = session.scalars(runs_stmt).all()
            if not runs:
                return {
                    "period_days": days_back,
                    "completed_runs": 0,
                    "avg_yield_pct": 0,
                    "avg_cost_per_output_unit": 0,
                }

            yields = []
            costs_per_unit = []

            for run in runs:
                if run.output_quantity and run.input_quantity and run.input_quantity > 0:
                    yield_pct = (run.output_quantity / run.input_quantity) * 100
                    yields.append(yield_pct)

                    # Query cost events for this run
                    cost_events = session.scalars(
                        select(ExtractionCostEvent).where(
                            ExtractionCostEvent.run_id == run.id,
                        )
                    ).all()
                    total_cost = sum((e.amount_usd or 0) for e in cost_events)
                    cost_per_unit = total_cost / run.output_quantity if run.output_quantity > 0 else 0
                    costs_per_unit.append(cost_per_unit)

            avg_yield = sum(yields) / len(yields) if yields else 0
            avg_cost_per_unit = sum(costs_per_unit) / len(costs_per_unit) if costs_per_unit else 0

            return {
                "period_days": days_back,
                "completed_runs": len(runs),
                "avg_yield_pct": round(avg_yield, 1),
                "avg_cost_per_output_unit": round(avg_cost_per_unit, 2),
                "best_yield_pct": round(max(yields), 1) if yields else 0,
                "worst_yield_pct": round(min(yields), 1) if yields else 0,
            }
