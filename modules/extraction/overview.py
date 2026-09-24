"""Bounded, tenant-scoped projection of canonical Extraction records.

One session and a fixed query budget replace per-run repository fan-out.
This is a read model, not a new ledger. Preserve the existing overview's
mass, output-status, manual-fallback and valuation semantics.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, case, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Product
from modules.product_master.models import ProductValueEvent
from modules.traceability.models import TraceabilityTransaction
from .models import (ExtractionCostEvent, ExtractionQAEvent, ExtractionRun,
    ExtractionRunInput, ExtractionRunOutput, ExtractionTollJob)
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
    engine: Engine, organization_id: str, facility_id: str, *, limit: int = 500,
) -> tuple[list[ExtractionRun], dict[str, OverviewFacts]]:
    """At most 500 runs, ten SQL statements, one checked-out connection.

    Child aggregates are independently tenant/facility scoped. Historical event
    bodies and process-resource details are not fetched for a summary screen.
    Output/product and traceability joins remain inside the selected run scope.
    """
    if not organization_id or not facility_id:
        raise ValueError('Choose an organization and facility before reading Extraction.')
    if not 1 <= limit <= 500:
        raise ValueError('Extraction overview limit must be between 1 and 500.')
    with Session(engine) as session:
        runs = list(session.scalars(select(ExtractionRun).where(
            ExtractionRun.organization_id == organization_id,
            ExtractionRun.facility_id == facility_id,
        ).order_by(ExtractionRun.updated_at.desc()).limit(limit)))
        facts = {run.id: OverviewFacts() for run in runs}
        if not runs:
            return runs, facts
        ids = list(facts)

        def scope(model):
            return (model.organization_id == organization_id,
                    model.facility_id == facility_id, model.run_id.in_(ids))

        for rid, quantity in session.execute(select(ExtractionRunInput.run_id,
                func.sum(ExtractionRunInput.consumed_quantity))
                .where(*scope(ExtractionRunInput)).group_by(ExtractionRunInput.run_id)):
            facts[rid].consumed = float(quantity or 0)

        valued_outputs = []
        for rid, pid, status, quantity in session.execute(select(
                ExtractionRunOutput.run_id, ExtractionRunOutput.product_id,
                ExtractionRunOutput.status, func.sum(ExtractionRunOutput.quantity))
                .where(*scope(ExtractionRunOutput)).group_by(ExtractionRunOutput.run_id,
                    ExtractionRunOutput.product_id, ExtractionRunOutput.status)):
            quantity = float(quantity or 0)
            if status != 'destroyed':
                facts[rid].recorded_output += quantity
            if status in OUTPUT_ACTIVE_STATUSES:
                facts[rid].active_output += quantity
            if status not in {'waste', 'destroyed'}:
                valued_outputs.append((rid, pid, quantity))

        for rid, amount in session.execute(select(ExtractionCostEvent.run_id,
                func.sum(ExtractionCostEvent.amount_usd))
                .where(*scope(ExtractionCostEvent)).group_by(ExtractionCostEvent.run_id)):
            facts[rid].total_cogs = float(amount or 0)

        for rid, failed, passed in session.execute(select(ExtractionQAEvent.run_id,
                func.max(case((ExtractionQAEvent.result == 'failed', 1), else_=0)),
                func.max(case((ExtractionQAEvent.result == 'passed', 1), else_=0)))
                .where(*scope(ExtractionQAEvent)).group_by(ExtractionQAEvent.run_id)):
            facts[rid].qa_failed, facts[rid].qa_passed = bool(failed), bool(passed)

        for toll in session.scalars(select(ExtractionTollJob).where(*scope(ExtractionTollJob))):
            facts[toll.run_id].toll = toll

        tx = TraceabilityTransaction
        tx_scope = (tx.organization_id == organization_id, tx.facility_id == facility_id)
        for rid, count in session.execute(select(tx.entity_id, func.count(tx.id))
                .where(*tx_scope, tx.entity_type == 'extraction_run', tx.entity_id.in_(ids))
                .group_by(tx.entity_id)):
            facts[rid].traceability_count += int(count)
        for rid, count in session.execute(select(ExtractionRunOutput.run_id, func.count(tx.id))
                .join(tx, (tx.entity_id == ExtractionRunOutput.id) & (tx.entity_type == 'extraction_output'))
                .where(*scope(ExtractionRunOutput), *tx_scope).group_by(ExtractionRunOutput.run_id)):
            facts[rid].traceability_count += int(count)

        if valued_outputs:
            # Use a scoped subquery instead of an unbounded product-ID parameter list.
            products = select(ExtractionRunOutput.product_id).where(
                *scope(ExtractionRunOutput), ExtractionRunOutput.status.notin_(('waste', 'destroyed')))
            values = ProductValueEvent
            ranked = select(values.product_id.label('product_id'), values.value_type.label('kind'),
                values.amount.label('amount'), func.row_number().over(
                    partition_by=(values.product_id, values.value_type),
                    order_by=values.effective_at.desc()).label('position')).where(
                values.organization_id == organization_id, values.product_id.in_(products),
                values.value_type.in_(('wholesale_price', 'retail_price'))).subquery()
            prices = {(pid, kind): float(amount or 0) for pid, kind, amount in session.execute(
                select(ranked.c.product_id, ranked.c.kind, ranked.c.amount).where(ranked.c.position == 1))}
            fallback = dict(session.execute(select(Product.id, Product.retail_price).where(
                Product.organization_id == organization_id, Product.id.in_(products))).all())
            for rid, pid, quantity in valued_outputs:
                unit_value = next((prices[(pid, kind)] for kind in ('wholesale_price', 'retail_price')
                                   if prices.get((pid, kind), 0) > 0), float(fallback.get(pid) or 0))
                if unit_value > 0:
                    facts[rid].projected_value += quantity * unit_value
        return runs, facts
