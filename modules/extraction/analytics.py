"""Deterministic extraction command-center aggregates and exception ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.traceability.models import TraceabilityTransaction

from .models import (
    ExtractionCostEvent,
    ExtractionQAEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionStageEvent,
)


@dataclass(frozen=True)
class ExtractionException:
    severity: str
    priority: int
    run_id: str
    batch_number: str
    title: str
    detail: str
    action: str


SEVERITY_PRIORITY = {"critical": 100, "warning": 60, "review": 30, "info": 10}


def _age_hours(value: datetime | None) -> float | None:
    if value is None:
        return None
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0.0, (now - value).total_seconds() / 3600.0)


def build_run_board(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    include_closed: bool = True,
    limit: int = 500,
) -> pd.DataFrame:
    """Return one decision row per durable extraction run without N+1 UI queries."""

    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with session_factory() as session:
        statement = select(ExtractionRun).where(
            ExtractionRun.organization_id == organization_id,
            ExtractionRun.facility_id == facility_id,
        )
        if not include_closed:
            statement = statement.where(
                ExtractionRun.status.in_(("planned", "queued", "active", "hold", "qa"))
            )
        runs = list(
            session.scalars(
                statement.order_by(ExtractionRun.updated_at.desc()).limit(max(1, min(int(limit), 2000)))
            )
        )
        if not runs:
            return pd.DataFrame()
        run_ids = [run.id for run in runs]

        input_rows = session.execute(
            select(
                ExtractionRunInput.run_id,
                func.coalesce(func.sum(ExtractionRunInput.reserved_quantity), 0.0),
                func.coalesce(func.sum(ExtractionRunInput.consumed_quantity), 0.0),
                func.coalesce(func.sum(ExtractionRunInput.input_cost_usd), 0.0),
            )
            .where(ExtractionRunInput.run_id.in_(run_ids))
            .group_by(ExtractionRunInput.run_id)
        ).all()
        input_map = {
            run_id: {
                "reserved": float(reserved or 0.0),
                "consumed": float(consumed or 0.0),
                "material_cost": float(material_cost or 0.0),
            }
            for run_id, reserved, consumed, material_cost in input_rows
        }

        output_rows = session.execute(
            select(
                ExtractionRunOutput.run_id,
                func.coalesce(func.sum(ExtractionRunOutput.quantity), 0.0),
                func.count(ExtractionRunOutput.id),
                func.coalesce(func.sum(ExtractionRunOutput.output_cost_usd), 0.0),
            )
            .where(
                ExtractionRunOutput.run_id.in_(run_ids),
                ExtractionRunOutput.status != "destroyed",
            )
            .group_by(ExtractionRunOutput.run_id)
        ).all()
        output_map = {
            run_id: {
                "quantity": float(quantity or 0.0),
                "count": int(count or 0),
                "allocated_cogs": float(cogs or 0.0),
            }
            for run_id, quantity, count, cogs in output_rows
        }

        cost_rows = session.execute(
            select(
                ExtractionCostEvent.run_id,
                func.coalesce(func.sum(ExtractionCostEvent.amount_usd), 0.0),
            )
            .where(ExtractionCostEvent.run_id.in_(run_ids))
            .group_by(ExtractionCostEvent.run_id)
        ).all()
        cost_map = {run_id: float(amount or 0.0) for run_id, amount in cost_rows}

        qa_rows = session.execute(
            select(
                ExtractionQAEvent.run_id,
                func.count(ExtractionQAEvent.id),
                func.max(ExtractionQAEvent.occurred_at),
            )
            .where(ExtractionQAEvent.run_id.in_(run_ids))
            .group_by(ExtractionQAEvent.run_id)
        ).all()
        qa_map = {run_id: {"count": int(count), "last": last} for run_id, count, last in qa_rows}

        stage_rows = session.execute(
            select(
                ExtractionStageEvent.run_id,
                func.max(ExtractionStageEvent.occurred_at),
            )
            .where(ExtractionStageEvent.run_id.in_(run_ids))
            .group_by(ExtractionStageEvent.run_id)
        ).all()
        stage_map = {run_id: last for run_id, last in stage_rows}

        trace_rows = session.execute(
            select(
                TraceabilityTransaction.entity_id,
                TraceabilityTransaction.status,
                func.count(TraceabilityTransaction.id),
            )
            .where(
                TraceabilityTransaction.organization_id == organization_id,
                TraceabilityTransaction.facility_id == facility_id,
                TraceabilityTransaction.entity_type == "extraction_run",
                TraceabilityTransaction.entity_id.in_(run_ids),
            )
            .group_by(TraceabilityTransaction.entity_id, TraceabilityTransaction.status)
        ).all()
        trace_map: dict[str, dict[str, int]] = {}
        for entity_id, status, count in trace_rows:
            trace_map.setdefault(str(entity_id), {})[str(status)] = int(count or 0)

        # Output package transactions point at extraction_output IDs, so map those
        # back to their parent run before summarizing provider health.
        output_to_run = dict(
            session.execute(
                select(ExtractionRunOutput.id, ExtractionRunOutput.run_id).where(
                    ExtractionRunOutput.run_id.in_(run_ids)
                )
            ).all()
        )
        output_ids = list(output_to_run)
        if output_ids:
            output_trace_rows = session.execute(
                select(
                    TraceabilityTransaction.entity_id,
                    TraceabilityTransaction.status,
                    func.count(TraceabilityTransaction.id),
                )
                .where(
                    TraceabilityTransaction.organization_id == organization_id,
                    TraceabilityTransaction.facility_id == facility_id,
                    TraceabilityTransaction.entity_type == "extraction_output",
                    TraceabilityTransaction.entity_id.in_(output_ids),
                )
                .group_by(TraceabilityTransaction.entity_id, TraceabilityTransaction.status)
            ).all()
            for entity_id, status, count in output_trace_rows:
                parent_run_id = output_to_run.get(str(entity_id))
                if parent_run_id:
                    trace_map.setdefault(parent_run_id, {})[str(status)] = (
                        trace_map.setdefault(parent_run_id, {}).get(str(status), 0) + int(count or 0)
                    )

        rows: list[dict[str, Any]] = []
        for run in runs:
            input_info = input_map.get(run.id, {})
            output_info = output_map.get(run.id, {})
            consumed = float(input_info.get("consumed", 0.0))
            output_qty = float(output_info.get("quantity", 0.0))
            yield_pct = output_qty / consumed * 100.0 if consumed > 0 else 0.0
            total_cogs = float(cost_map.get(run.id, 0.0))
            cost_per_output = total_cogs / output_qty if output_qty > 0 else 0.0
            trace = trace_map.get(run.id, {})
            trace_exceptions = int(trace.get("rejected", 0) + trace.get("reconciliation_required", 0))
            trace_in_flight = int(
                sum(trace.get(status, 0) for status in ("requested", "validated", "queued", "submitted", "accepted"))
            )
            if trace_exceptions:
                attention = "CRITICAL · Traceability"
                severity = "critical"
            elif run.status == "hold" or run.release_status == "rejected":
                attention = "CRITICAL · Hold"
                severity = "critical"
            elif run.status == "qa" or run.release_status == "pending":
                attention = "QA ACTION"
                severity = "warning"
            elif trace_in_flight:
                attention = "Traceability pending"
                severity = "review"
            elif run.status in {"planned", "queued"}:
                attention = "Ready to stage"
                severity = "info"
            else:
                attention = "Normal"
                severity = "info"

            last_activity = stage_map.get(run.id) or run.updated_at
            rows.append(
                {
                    "run_id": run.id,
                    "Run": run.batch_number,
                    "Method": run.method,
                    "Stage": run.current_stage_key.replace("_", " ").title(),
                    "Status": run.status.title(),
                    "Release": run.release_status.title(),
                    "Strain": run.strain,
                    "Reserved": float(input_info.get("reserved", 0.0)),
                    "Input": consumed,
                    "Output": output_qty,
                    "Yield %": yield_pct,
                    "COGS": total_cogs,
                    "Cost / Output": cost_per_output,
                    "Outputs": int(output_info.get("count", 0)),
                    "QA Events": int(qa_map.get(run.id, {}).get("count", 0)),
                    "Traceability Exceptions": trace_exceptions,
                    "Traceability Pending": trace_in_flight,
                    "Attention": attention,
                    "severity": severity,
                    "Last Activity": last_activity,
                    "Idle Hours": _age_hours(last_activity),
                }
            )
        return pd.DataFrame(rows)


def build_extraction_exceptions(board: pd.DataFrame) -> list[ExtractionException]:
    """Rank actionable run exceptions without AI deciding severity."""

    if board is None or board.empty:
        return []
    exceptions: list[ExtractionException] = []
    for _, row in board.iterrows():
        run_id = str(row.get("run_id") or "")
        batch = str(row.get("Run") or "Run")
        trace_errors = int(row.get("Traceability Exceptions") or 0)
        if trace_errors:
            exceptions.append(
                ExtractionException(
                    severity="critical",
                    priority=110 + trace_errors,
                    run_id=run_id,
                    batch_number=batch,
                    title=f"{batch}: traceability reconciliation required",
                    detail=f"{trace_errors} rejected or uncertain state-system action(s).",
                    action="Open Traceability",
                )
            )
        status = str(row.get("Status") or "").casefold()
        release = str(row.get("Release") or "").casefold()
        if status == "hold" or release == "rejected":
            exceptions.append(
                ExtractionException(
                    severity="critical",
                    priority=100,
                    run_id=run_id,
                    batch_number=batch,
                    title=f"{batch}: production / QA hold",
                    detail="The run is blocked from release until the hold is resolved.",
                    action="Open QA",
                )
            )
        elif status == "qa" or release == "pending":
            exceptions.append(
                ExtractionException(
                    severity="warning",
                    priority=70,
                    run_id=run_id,
                    batch_number=batch,
                    title=f"{batch}: QA release pending",
                    detail="Output is quarantined and cannot become available inventory until QA release.",
                    action="Open QA",
                )
            )
        idle_hours = row.get("Idle Hours")
        if pd.notna(idle_hours) and float(idle_hours) >= 48 and status in {"active", "queued", "planned"}:
            exceptions.append(
                ExtractionException(
                    severity="review",
                    priority=40 + min(20, int(float(idle_hours) // 24)),
                    run_id=run_id,
                    batch_number=batch,
                    title=f"{batch}: no recent stage activity",
                    detail=f"No durable stage event has been recorded for approximately {float(idle_hours):.0f} hours.",
                    action="Record Stage",
                )
            )
    return sorted(exceptions, key=lambda item: (-item.priority, item.batch_number))
