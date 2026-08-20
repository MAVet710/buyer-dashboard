"""Extraction performance intelligence beyond basic run logging.

This layer keeps performance math deterministic. It combines durable run data,
shared inventory COGS, Product Master pricing, and process-resource usage so the
operator can compare a run against its real peers and act from Run 360.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable

from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Product
from modules.product_master.models import ProductValueEvent

from .models import ExtractionCostEvent, ExtractionRun, ExtractionRunInput, ExtractionRunOutput
from .performance_models import ExtractionResourceEvent


RESOURCE_TYPES = {"solvent", "utility", "gas", "consumable", "water", "other"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if float(denominator) > 0 else 0.0


def _percentile_rank(value: float, peers: Iterable[float], *, higher_is_better: bool = True) -> float | None:
    values = [float(item) for item in peers if item is not None]
    if not values:
        return None
    if higher_is_better:
        wins = sum(1 for item in values if item <= float(value))
    else:
        wins = sum(1 for item in values if item >= float(value))
    return wins / len(values) * 100.0


def summarize_resource_events(events: Iterable[ExtractionResourceEvent | dict[str, Any]]) -> dict[str, Any]:
    """Summarize resource usage without hiding the underlying append-only events."""

    by_type: dict[str, dict[str, float]] = {}
    total_cost = 0.0
    solvent_used = 0.0
    solvent_recovered = 0.0
    for event in events:
        getter = event.get if isinstance(event, dict) else lambda key, default=None: getattr(event, key, default)
        kind = _clean(getter("resource_type")).casefold() or "other"
        quantity = max(0.0, float(getter("quantity", 0.0) or 0.0))
        recovered_raw = getter("recovered_quantity", None)
        recovered = max(0.0, float(recovered_raw or 0.0)) if recovered_raw is not None else 0.0
        cost = max(0.0, float(getter("cost_usd", 0.0) or 0.0))
        bucket = by_type.setdefault(kind, {"quantity": 0.0, "recovered": 0.0, "cost": 0.0})
        bucket["quantity"] += quantity
        bucket["recovered"] += recovered
        bucket["cost"] += cost
        total_cost += cost
        if kind == "solvent":
            solvent_used += quantity
            solvent_recovered += recovered
    recovery_pct = _safe_div(solvent_recovered, solvent_used) * 100.0 if solvent_used > 0 else 0.0
    return {
        "total_cost": total_cost,
        "solvent_used": solvent_used,
        "solvent_recovered": solvent_recovered,
        "solvent_recovery_pct": recovery_pct,
        "by_type": by_type,
    }


def benchmark_run_metrics(target: dict[str, Any], peers: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compare one run with like-for-like peers using transparent median benchmarks."""

    peer_rows = [dict(row) for row in peers if row]
    if not peer_rows:
        return {
            "peer_count": 0,
            "yield_median": None,
            "cost_per_output_median": None,
            "cycle_hours_median": None,
            "solvent_recovery_median": None,
            "yield_delta": None,
            "cost_delta": None,
            "cycle_delta": None,
            "solvent_recovery_delta": None,
            "yield_percentile": None,
            "cost_percentile": None,
        }

    def series(key: str, *, positive_only: bool = False) -> list[float]:
        values: list[float] = []
        for row in peer_rows:
            raw = row.get(key)
            if raw is None:
                continue
            value = float(raw)
            if positive_only and value <= 0:
                continue
            values.append(value)
        return values

    yields = series("yield_pct", positive_only=True)
    costs = series("cost_per_output", positive_only=True)
    cycles = series("cycle_hours", positive_only=True)
    recoveries = series("solvent_recovery_pct", positive_only=True)

    yield_med = median(yields) if yields else None
    cost_med = median(costs) if costs else None
    cycle_med = median(cycles) if cycles else None
    recovery_med = median(recoveries) if recoveries else None
    target_yield = float(target.get("yield_pct") or 0.0)
    target_cost = float(target.get("cost_per_output") or 0.0)
    target_cycle = float(target.get("cycle_hours") or 0.0)
    target_recovery = float(target.get("solvent_recovery_pct") or 0.0)

    return {
        "peer_count": len(peer_rows),
        "yield_median": yield_med,
        "cost_per_output_median": cost_med,
        "cycle_hours_median": cycle_med,
        "solvent_recovery_median": recovery_med,
        "yield_delta": target_yield - yield_med if yield_med is not None else None,
        "cost_delta": target_cost - cost_med if cost_med is not None and target_cost > 0 else None,
        "cycle_delta": target_cycle - cycle_med if cycle_med is not None and target_cycle > 0 else None,
        "solvent_recovery_delta": target_recovery - recovery_med if recovery_med is not None and target_recovery > 0 else None,
        "yield_percentile": _percentile_rank(target_yield, yields, higher_is_better=True) if target_yield > 0 else None,
        "cost_percentile": _percentile_rank(target_cost, costs, higher_is_better=False) if target_cost > 0 else None,
    }


class ExtractionPerformanceService:
    """Tenant-safe resource, economics and peer-comparison service."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def resource_table_ready(self) -> bool:
        try:
            return inspect(self.engine).has_table("extraction_resource_events")
        except Exception:
            return False

    def record_resource_usage(
        self,
        *,
        organization_id: str,
        facility_id: str,
        run_id: str,
        resource_type: str,
        resource_name: str,
        quantity: float,
        unit: str,
        actor: str,
        stage_key: str = "",
        recovered_quantity: float | None = None,
        cost_usd: float = 0.0,
        source_reference: str = "",
        notes: str = "",
    ) -> ExtractionResourceEvent:
        kind = _clean(resource_type).casefold()
        name = _clean(resource_name)
        clean_unit = _clean(unit)
        clean_actor = _clean(actor)
        qty = float(quantity)
        recovered = float(recovered_quantity) if recovered_quantity is not None else None
        amount = float(cost_usd)
        if kind not in RESOURCE_TYPES:
            raise ValueError("Unsupported extraction resource type.")
        if not name or not clean_unit or not clean_actor:
            raise ValueError("Resource name, unit, and actor are required.")
        if qty <= 0:
            raise ValueError("Resource quantity must be positive.")
        if recovered is not None and (recovered < 0 or recovered > qty):
            raise ValueError("Recovered quantity must be between zero and the amount used.")
        if amount < 0:
            raise ValueError("Resource cost cannot be negative.")

        with self._session_factory.begin() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            event = ExtractionResourceEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                stage_key=_clean(stage_key) or run.current_stage_key,
                resource_type=kind,
                resource_name=name,
                quantity=qty,
                unit=clean_unit,
                recovered_quantity=recovered,
                cost_usd=amount,
                source_reference=_clean(source_reference),
                notes=_clean(notes),
                actor=clean_actor,
            )
            session.add(event)
            session.flush()
            if amount > 0:
                cost_category = "packaging" if kind == "consumable" else "processing"
                session.add(
                    ExtractionCostEvent(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        run_id=run.id,
                        category=cost_category,
                        amount_usd=amount,
                        quantity=qty,
                        unit=clean_unit,
                        unit_rate_usd=_safe_div(amount, qty),
                        source_type="resource_usage",
                        source_id=event.id,
                        notes=f"{kind}: {name}",
                        actor=clean_actor,
                    )
                )
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="extraction_run",
                    entity_id=run.id,
                    action="resource_usage_recorded",
                    actor=clean_actor,
                    changes_json=(
                        f'{{"resource_type":"{kind}","resource_name":"{name}",'
                        f'"quantity":{qty},"unit":"{clean_unit}","cost_usd":{amount}}}'
                    ),
                )
            )
            session.flush()
            return event

    def list_resource_events(
        self,
        organization_id: str,
        facility_id: str,
        run_id: str,
    ) -> list[ExtractionResourceEvent]:
        if not self.resource_table_ready():
            return []
        with self._session_factory() as session:
            self._require_run(session, organization_id, facility_id, run_id)
            return list(
                session.scalars(
                    select(ExtractionResourceEvent)
                    .where(
                        ExtractionResourceEvent.organization_id == organization_id,
                        ExtractionResourceEvent.facility_id == facility_id,
                        ExtractionResourceEvent.run_id == run_id,
                    )
                    .order_by(ExtractionResourceEvent.occurred_at)
                )
            )

    def run_metrics(self, organization_id: str, facility_id: str, run_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            run = self._require_run(session, organization_id, facility_id, run_id)
            consumed = float(
                session.scalar(
                    select(func.coalesce(func.sum(ExtractionRunInput.consumed_quantity), 0.0)).where(
                        ExtractionRunInput.run_id == run.id
                    )
                )
                or 0.0
            )
            outputs = list(
                session.scalars(
                    select(ExtractionRunOutput).where(
                        ExtractionRunOutput.run_id == run.id,
                        ExtractionRunOutput.status.notin_(("waste", "destroyed")),
                    )
                )
            )
            output_qty = sum(max(0.0, float(output.quantity or 0.0)) for output in outputs)
            total_cogs = float(
                session.scalar(
                    select(func.coalesce(func.sum(ExtractionCostEvent.amount_usd), 0.0)).where(
                        ExtractionCostEvent.run_id == run.id
                    )
                )
                or 0.0
            )
            resource_events: list[ExtractionResourceEvent] = []
            if self.resource_table_ready():
                resource_events = list(
                    session.scalars(
                        select(ExtractionResourceEvent).where(ExtractionResourceEvent.run_id == run.id)
                    )
                )
            resources = summarize_resource_events(resource_events)
            value = 0.0
            unmapped_outputs: list[str] = []
            valuation_basis: dict[str, str] = {}
            for output in outputs:
                unit_value, basis = self._latest_output_value(session, organization_id, output.product_id)
                if unit_value <= 0:
                    unmapped_outputs.append(output.output_label)
                    continue
                value += float(output.quantity or 0.0) * unit_value
                valuation_basis[output.id] = basis
            cycle_hours = self._cycle_hours(run)
            yield_pct = _safe_div(output_qty, consumed) * 100.0 if consumed > 0 else 0.0
            cost_per_output = _safe_div(total_cogs, output_qty)
            gross_profit = value - total_cogs
            margin_pct = _safe_div(gross_profit, value) * 100.0 if value > 0 else 0.0
            resource_cost_per_output = _safe_div(float(resources["total_cost"]), output_qty)
            solvent_per_output = _safe_div(float(resources["solvent_used"]), output_qty)
            return {
                "run_id": run.id,
                "batch_number": run.batch_number,
                "workflow_key": run.workflow_key,
                "method": run.method,
                "status": run.status,
                "consumed_input": consumed,
                "output_quantity": output_qty,
                "yield_pct": yield_pct,
                "total_cogs": total_cogs,
                "cost_per_output": cost_per_output,
                "projected_output_value": value,
                "projected_gross_profit": gross_profit,
                "projected_margin_pct": margin_pct,
                "cycle_hours": cycle_hours,
                "resource_cost": float(resources["total_cost"]),
                "resource_cost_per_output": resource_cost_per_output,
                "solvent_used": float(resources["solvent_used"]),
                "solvent_recovered": float(resources["solvent_recovered"]),
                "solvent_recovery_pct": float(resources["solvent_recovery_pct"]),
                "solvent_per_output": solvent_per_output,
                "resource_by_type": resources["by_type"],
                "unmapped_outputs": unmapped_outputs,
                "valuation_basis": valuation_basis,
            }

    def peer_benchmark(
        self,
        organization_id: str,
        facility_id: str,
        run_id: str,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        target = self.run_metrics(organization_id, facility_id, run_id)
        with self._session_factory() as session:
            peer_ids = list(
                session.scalars(
                    select(ExtractionRun.id)
                    .where(
                        ExtractionRun.organization_id == organization_id,
                        ExtractionRun.facility_id == facility_id,
                        ExtractionRun.workflow_key == target["workflow_key"],
                        ExtractionRun.id != run_id,
                        ExtractionRun.status.notin_(("cancelled", "failed")),
                    )
                    .order_by(ExtractionRun.completed_at.desc().nullslast(), ExtractionRun.updated_at.desc())
                    .limit(max(1, min(int(limit), 200)))
                )
            )
        peers = [self.run_metrics(organization_id, facility_id, peer_id) for peer_id in peer_ids]
        benchmark = benchmark_run_metrics(target, peers)
        benchmark["target"] = target
        benchmark["peers"] = peers
        return benchmark

    def compare_runs(
        self,
        organization_id: str,
        facility_id: str,
        run_ids: Iterable[str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run_id in dict.fromkeys(_clean(item) for item in run_ids if _clean(item)):
            rows.append(self.run_metrics(organization_id, facility_id, run_id))
        return rows

    @staticmethod
    def _cycle_hours(run: ExtractionRun) -> float:
        start = run.started_at or run.created_at
        end = run.completed_at or run.updated_at
        if start is None or end is None:
            return 0.0
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - start).total_seconds() / 3600.0)

    @staticmethod
    def _require_run(session, organization_id: str, facility_id: str, run_id: str) -> ExtractionRun:
        run = session.get(ExtractionRun, run_id)
        if not run or run.organization_id != organization_id or run.facility_id != facility_id:
            raise ValueError("Extraction run was not found in the active facility.")
        return run

    @staticmethod
    def _latest_output_value(session, organization_id: str, product_id: str) -> tuple[float, str]:
        for kind in ("wholesale_price", "retail_price"):
            amount = session.scalar(
                select(ProductValueEvent.amount)
                .where(
                    ProductValueEvent.organization_id == organization_id,
                    ProductValueEvent.product_id == product_id,
                    ProductValueEvent.value_type == kind,
                )
                .order_by(ProductValueEvent.effective_at.desc())
                .limit(1)
            )
            if amount is not None and float(amount) > 0:
                return float(amount), kind
        product = session.get(Product, product_id)
        if product and product.organization_id == organization_id and float(product.retail_price or 0.0) > 0:
            return float(product.retail_price), "product_retail_price"
        return 0.0, "unmapped"
