"""Profitability analytics router for vertical cannabis operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine
from modules.coman.models import InventoryLot, Product
from modules.commercial_finance.models import CommercialInvoice, CommercialInvoiceLine
from modules.extraction.models import ExtractionCostEvent, ExtractionRun
from modules.production_erp.models import ProductionCostEvent

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(get_production_context)])


@router.get("/supply-chain-margin")
def get_supply_chain_margin(
    days_back: int = Query(30, ge=7, le=365),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Analyze supply chain margin (revenue vs COGS)."""
    period_end = datetime.now(tz=timezone.utc).date()
    period_start = period_end - timedelta(days=days_back)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    try:
        # Revenue
        revenue = float(
            db.scalar(
                select(func.sum(CommercialInvoiceLine.quantity * CommercialInvoiceLine.unit_price))
                .join(CommercialInvoice)
                .where(
                    CommercialInvoice.organization_id == context.organization_id,
                    CommercialInvoice.facility_id == context.facility_id,
                    CommercialInvoice.issue_date >= period_start,
                    CommercialInvoice.issue_date <= period_end,
                )
            )
            or 0
        )

        # Production COGS
        prod_cogs = float(
            db.scalar(
                select(func.sum(ProductionCostEvent.amount_usd)).where(
                    ProductionCostEvent.organization_id == context.organization_id,
                    ProductionCostEvent.facility_id == context.facility_id,
                    ProductionCostEvent.category.in_(["material", "labor", "overhead", "packaging"]),
                    ProductionCostEvent.occurred_at >= period_start,
                    ProductionCostEvent.occurred_at <= period_end,
                )
            )
            or 0
        )

        # Extraction COGS
        ext_cogs = float(
            db.scalar(
                select(func.sum(ExtractionCostEvent.amount_usd))
                .join(ExtractionRun)
                .where(
                    ExtractionCostEvent.organization_id == context.organization_id,
                    ExtractionCostEvent.facility_id == context.facility_id,
                    ExtractionCostEvent.category.in_(["material", "labor"]),
                    ExtractionRun.completed_at >= period_start,
                    ExtractionRun.completed_at <= period_end,
                )
            )
            or 0
        )

        total_cogs = prod_cogs + ext_cogs
        margin = revenue - total_cogs
        margin_pct = (margin / revenue * 100) if revenue > 0 else 0

        return {
            "period_days": days_back,
            "period_end": period_end.isoformat(),
            "total_revenue": round(revenue, 2),
            "total_cogs": round(total_cogs, 2),
            "gross_margin": round(margin, 2),
            "gross_margin_pct": round(margin_pct, 1),
        }
    finally:
        db.close()


@router.get("/product-profitability")
def get_product_profitability(
    days_back: int = Query(30, ge=7, le=365),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> list[dict[str, Any]]:
    """Analyze profitability by product SKU."""
    period_end = datetime.now(tz=timezone.utc).date()
    period_start = period_end - timedelta(days=days_back)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    try:
        results = []
        sales = db.execute(
            select(
                CommercialInvoiceLine.product_id,
                Product.name,
                Product.sku,
                func.sum(CommercialInvoiceLine.quantity).label("units_sold"),
                func.sum(CommercialInvoiceLine.quantity * CommercialInvoiceLine.unit_price).label("revenue"),
            )
            .join(Product)
            .join(CommercialInvoice)
            .where(
                CommercialInvoice.organization_id == context.organization_id,
                CommercialInvoice.facility_id == context.facility_id,
                CommercialInvoice.issue_date >= period_start,
                CommercialInvoice.issue_date <= period_end,
            )
            .group_by(CommercialInvoiceLine.product_id, Product.name, Product.sku)
        ).fetchall()

        for pid, name, sku, units, revenue in sales:
            revenue = float(revenue or 0)
            units = float(units or 0)

            avg_cost = float(
                db.scalar(
                    select(func.avg(InventoryLot.unit_cost)).where(
                        InventoryLot.organization_id == context.organization_id,
                        InventoryLot.facility_id == context.facility_id,
                        InventoryLot.product_id == pid,
                    )
                )
                or 0
            )

            cogs = units * avg_cost
            margin = revenue - cogs
            margin_pct = (margin / revenue * 100) if revenue > 0 else 0

            results.append({
                "product_id": str(pid),
                "product_name": str(name or "—"),
                "sku": str(sku or "—"),
                "units_sold": round(units, 2),
                "revenue": round(revenue, 2),
                "cogs": round(cogs, 2),
                "margin": round(margin, 2),
                "margin_pct": round(margin_pct, 1),
            })

        return sorted(results, key=lambda x: x["margin"], reverse=True)
    finally:
        db.close()


@router.get("/production-cost-analysis")
def get_production_cost_analysis(
    days_back: int = Query(30, ge=7, le=365),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Analyze production costs by category."""
    period_end = datetime.now(tz=timezone.utc).date()
    period_start = period_end - timedelta(days=days_back)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    try:
        breakdown = {}
        total = 0.0

        costs = db.execute(
            select(
                ProductionCostEvent.category,
                func.sum(ProductionCostEvent.amount_usd).label("total"),
                func.count(ProductionCostEvent.id).label("count"),
            )
            .where(
                ProductionCostEvent.organization_id == context.organization_id,
                ProductionCostEvent.facility_id == context.facility_id,
                ProductionCostEvent.occurred_at >= period_start,
                ProductionCostEvent.occurred_at <= period_end,
            )
            .group_by(ProductionCostEvent.category)
        ).fetchall()

        for category, amount, count in costs:
            amount = float(amount or 0)
            breakdown[str(category)] = {"total_usd": round(amount, 2), "events": int(count or 0)}
            total += amount

        return {
            "period_days": days_back,
            "period_end": period_end.isoformat(),
            "total_production_cost": round(total, 2),
            "breakdown": breakdown,
        }
    finally:
        db.close()


@router.get("/extraction-efficiency")
def get_extraction_efficiency(
    days_back: int = Query(30, ge=7, le=365),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Analyze extraction yield efficiency and cost per output unit."""
    period_end = datetime.now(tz=timezone.utc).date()
    period_start = period_end - timedelta(days=days_back)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    try:
        runs = db.scalars(
            select(ExtractionRun).where(
                ExtractionRun.organization_id == context.organization_id,
                ExtractionRun.facility_id == context.facility_id,
                ExtractionRun.completed_at >= period_start,
                ExtractionRun.completed_at <= period_end,
            )
        ).all()

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

                total_cost = sum(
                    float(e.amount_usd or 0)
                    for e in db.scalars(
                        select(ExtractionCostEvent).where(ExtractionCostEvent.run_id == run.id)
                    ).all()
                )
                cost_per_unit = total_cost / run.output_quantity if run.output_quantity > 0 else 0
                costs_per_unit.append(cost_per_unit)

        avg_yield = sum(yields) / len(yields) if yields else 0
        avg_cost = sum(costs_per_unit) / len(costs_per_unit) if costs_per_unit else 0

        return {
            "period_days": days_back,
            "completed_runs": len(runs),
            "avg_yield_pct": round(avg_yield, 1),
            "avg_cost_per_output_unit": round(avg_cost, 2),
            "best_yield_pct": round(max(yields), 1) if yields else 0,
            "worst_yield_pct": round(min(yields), 1) if yields else 0,
        }
    finally:
        db.close()


@router.get("/insights")
def get_insights(
    days_back: int = Query(30, ge=7, le=365),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:
    """Generate operational insights from profitability data."""
    margin = get_supply_chain_margin(days_back, context, engine)
    products = get_product_profitability(days_back, context, engine)
    extraction = get_extraction_efficiency(days_back, context, engine)

    insights = []
    warnings = []

    if margin["gross_margin_pct"] < 30:
        warnings.append("Margin is below 30% — review pricing or cost structure")
    elif margin["gross_margin_pct"] > 50:
        insights.append("Strong margin performance — continue current strategy")

    if products:
        losers = [p for p in products if p["margin_pct"] < 0]
        if losers:
            warnings.append(f"{len(losers)} product(s) with negative margin — review pricing")

    if extraction["completed_runs"] > 0:
        if extraction["avg_yield_pct"] < 65:
            warnings.append("Extraction yield below benchmark (65%) — review process parameters")
        elif extraction["avg_yield_pct"] > 70:
            insights.append(f"Excellent extraction efficiency at {extraction['avg_yield_pct']:.1f}%")

    return {
        "period_days": days_back,
        "insights": insights,
        "warnings": warnings,
    }
