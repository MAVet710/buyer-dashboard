"""Bounded, tenant-scoped projection of canonical Extraction records.

One SQL statement with pre-aggregated subqueries replaces per-run and
per-domain round trips. This is a read model, not a second ledger.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, and_, case, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Product
from modules.product_master.models import ProductValueEvent
from modules.traceability.models import TraceabilityTransaction
from .models import (
    ExtractionCostEvent,
    ExtractionQAEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionTollJob,
)
from .repository import OUTPUT_ACTIVE_STATUSES


@dataclass
class OverviewFacts:
    consumed: float = 0.0
    recorded_output: float = 0.0
    active_output: float = 0.0
    total_cogs: float = 0.0
    projected_value: float = 0.0
    qa_failed: bool = False
    qa_passed: bool = False
    traceability_count: int = 0
    toll: ExtractionTollJob | None = None


def load_extraction_overview(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    limit: int = 500,
) -> tuple[list[ExtractionRun], dict[str, OverviewFacts]]:
    """Load the bounded overview with one database round trip."""
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before reading Extraction.")
    if not 1 <= limit <= 500:
        raise ValueError("Extraction overview limit must be between 1 and 500.")

    selected = (
        select(ExtractionRun.id)
        .where(
            ExtractionRun.organization_id == organization_id,
            ExtractionRun.facility_id == facility_id,
        )
        .order_by(ExtractionRun.updated_at.desc())
        .limit(limit)
        .cte("selected_extraction_runs")
    )
    selected_ids = select(selected.c.id)
    input_agg = (
        select(
            ExtractionRunInput.run_id.label("run_id"),
            func.sum(ExtractionRunInput.consumed_quantity).label("consumed"),
        )
        .where(
            ExtractionRunInput.organization_id == organization_id,
            ExtractionRunInput.facility_id == facility_id,
            ExtractionRunInput.run_id.in_(selected_ids),
        )
        .group_by(ExtractionRunInput.run_id)
        .subquery()
    )

    value_products = select(ExtractionRunOutput.product_id).where(
        ExtractionRunOutput.organization_id == organization_id,
        ExtractionRunOutput.facility_id == facility_id,
        ExtractionRunOutput.run_id.in_(selected_ids),
        ExtractionRunOutput.status.notin_(("waste", "destroyed")),
    )
    ranked_values = (
        select(
            ProductValueEvent.product_id.label("product_id"),
            ProductValueEvent.value_type.label("value_type"),
            ProductValueEvent.amount.label("amount"),
            func.row_number()
            .over(
                partition_by=(ProductValueEvent.product_id, ProductValueEvent.value_type),
                order_by=ProductValueEvent.effective_at.desc(),
            )
            .label("position"),
        )
        .where(
            ProductValueEvent.organization_id == organization_id,
            ProductValueEvent.product_id.in_(value_products),
            ProductValueEvent.value_type.in_(("wholesale_price", "retail_price")),
        )
        .subquery()
    )
    prices = (
        select(
            ranked_values.c.product_id,
            func.max(
                case(
                    (ranked_values.c.value_type == "wholesale_price", ranked_values.c.amount)
                )
            ).label("wholesale_price"),
            func.max(
                case(
                    (ranked_values.c.value_type == "retail_price", ranked_values.c.amount)
                )
            ).label("retail_price"),
        )
        .where(ranked_values.c.position == 1)
        .group_by(ranked_values.c.product_id)
        .subquery()
    )
    unit_value = case(
        (prices.c.wholesale_price > 0, prices.c.wholesale_price),
        (prices.c.retail_price > 0, prices.c.retail_price),
        else_=func.coalesce(Product.retail_price, 0.0),
    )
    output_agg = (
        select(
            ExtractionRunOutput.run_id.label("run_id"),
            func.sum(
                case(
                    (ExtractionRunOutput.status != "destroyed", ExtractionRunOutput.quantity),
                    else_=0.0,
                )
            ).label("recorded_output"),
            func.sum(
                case(
                    (
                        ExtractionRunOutput.status.in_(OUTPUT_ACTIVE_STATUSES),
                        ExtractionRunOutput.quantity,
                    ),
                    else_=0.0,
                )
            ).label("active_output"),
            func.sum(
                case(
                    (
                        ExtractionRunOutput.status.notin_(("waste", "destroyed")),
                        ExtractionRunOutput.quantity * unit_value,
                    ),
                    else_=0.0,
                )
            ).label("projected_value"),
        )
        .outerjoin(prices, prices.c.product_id == ExtractionRunOutput.product_id)
        .outerjoin(
            Product,
            and_(
                Product.id == ExtractionRunOutput.product_id,
                Product.organization_id == organization_id,
            ),
        )
        .where(
            ExtractionRunOutput.organization_id == organization_id,
            ExtractionRunOutput.facility_id == facility_id,
            ExtractionRunOutput.run_id.in_(selected_ids),
        )
        .group_by(ExtractionRunOutput.run_id)
        .subquery()
    )

    cost_agg = (
        select(
            ExtractionCostEvent.run_id.label("run_id"),
            func.sum(ExtractionCostEvent.amount_usd).label("total_cogs"),
        )
        .where(
            ExtractionCostEvent.organization_id == organization_id,
            ExtractionCostEvent.facility_id == facility_id,
            ExtractionCostEvent.run_id.in_(selected_ids),
        )
        .group_by(ExtractionCostEvent.run_id)
        .subquery()
    )
    qa_agg = (
        select(
            ExtractionQAEvent.run_id.label("run_id"),
            func.max(
                case((ExtractionQAEvent.result == "failed", 1), else_=0)
            ).label("qa_failed"),
            func.max(
                case((ExtractionQAEvent.result == "passed", 1), else_=0)
            ).label("qa_passed"),
        )
        .where(
            ExtractionQAEvent.organization_id == organization_id,
            ExtractionQAEvent.facility_id == facility_id,
            ExtractionQAEvent.run_id.in_(selected_ids),
        )
        .group_by(ExtractionQAEvent.run_id)
        .subquery()
    )

    tx = TraceabilityTransaction
    run_trace_agg = (
        select(
            tx.entity_id.label("run_id"),
            func.count(tx.id).label("count"),
        )
        .where(
            tx.organization_id == organization_id,
            tx.facility_id == facility_id,
            tx.entity_type == "extraction_run",
            tx.entity_id.in_(selected_ids),
        )
        .group_by(tx.entity_id)
        .subquery()
    )
    output_trace_agg = (
        select(
            ExtractionRunOutput.run_id.label("run_id"),
            func.count(tx.id).label("count"),
        )
        .join(
            tx,
            and_(
                tx.entity_id == ExtractionRunOutput.id,
                tx.entity_type == "extraction_output",
                tx.organization_id == organization_id,
                tx.facility_id == facility_id,
            ),
        )
        .where(
            ExtractionRunOutput.organization_id == organization_id,
            ExtractionRunOutput.facility_id == facility_id,
            ExtractionRunOutput.run_id.in_(selected_ids),
        )
        .group_by(ExtractionRunOutput.run_id)
        .subquery()
    )

    stmt = (
        select(
            ExtractionRun,
            input_agg.c.consumed,
            output_agg.c.recorded_output,
            output_agg.c.active_output,
            cost_agg.c.total_cogs,
            output_agg.c.projected_value,
            qa_agg.c.qa_failed,
            qa_agg.c.qa_passed,
            run_trace_agg.c.count,
            output_trace_agg.c.count,
            ExtractionTollJob,
        )
        .join(selected, selected.c.id == ExtractionRun.id)
        .outerjoin(input_agg, input_agg.c.run_id == ExtractionRun.id)
        .outerjoin(output_agg, output_agg.c.run_id == ExtractionRun.id)
        .outerjoin(cost_agg, cost_agg.c.run_id == ExtractionRun.id)
        .outerjoin(qa_agg, qa_agg.c.run_id == ExtractionRun.id)
        .outerjoin(run_trace_agg, run_trace_agg.c.run_id == ExtractionRun.id)
        .outerjoin(output_trace_agg, output_trace_agg.c.run_id == ExtractionRun.id)
        .outerjoin(
            ExtractionTollJob,
            and_(
                ExtractionTollJob.run_id == ExtractionRun.id,
                ExtractionTollJob.organization_id == organization_id,
                ExtractionTollJob.facility_id == facility_id,
            ),
        )
        .order_by(ExtractionRun.updated_at.desc())
    )

    runs: list[ExtractionRun] = []
    facts: dict[str, OverviewFacts] = {}
    with Session(engine) as session:
        for row in session.execute(stmt):
            run = row[0]
            toll = row[10]
            runs.append(run)
            facts[run.id] = OverviewFacts(
                consumed=float(row[1] or 0),
                recorded_output=float(row[2] or 0),
                active_output=float(row[3] or 0),
                total_cogs=float(row[4] or 0),
                projected_value=float(row[5] or 0),
                qa_failed=bool(row[6]),
                qa_passed=bool(row[7]),
                traceability_count=int(row[8] or 0) + int(row[9] or 0),
                toll=toll,
            )
    return runs, facts
