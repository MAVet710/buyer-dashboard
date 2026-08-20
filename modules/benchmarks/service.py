"""Aggregate capture and opt-in network benchmarking.

Only aggregate observations are stored. Network results never return another
organization's raw value or identity and are suppressed below the cohort floor.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.extraction.models import ExtractionRun
from modules.extraction.performance import ExtractionPerformanceService
from modules.migration_center.models import MigrationSalesHistory
from modules.production_erp.service import ProductionERPService

from .models import BenchmarkObservation, BenchmarkSetting


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    fraction = pos - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def _rank(value: float, values: Iterable[float], higher_is_better: bool = True) -> float | None:
    vals = [float(v) for v in values]
    if not vals:
        return None
    wins = sum((v <= value) if higher_is_better else (v >= value) for v in vals)
    return wins / len(vals) * 100.0


class BenchmarkService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def setting(self, organization_id: str) -> BenchmarkSetting | None:
        with self._sessions() as session:
            return session.scalar(select(BenchmarkSetting).where(BenchmarkSetting.organization_id == organization_id))

    def set_opt_in(self, *, organization_id: str, share: bool, actor: str, minimum_cohort_size: int = 5) -> BenchmarkSetting:
        minimum = max(3, min(int(minimum_cohort_size), 50))
        with self._sessions.begin() as session:
            row = session.scalar(select(BenchmarkSetting).where(BenchmarkSetting.organization_id == organization_id))
            if row is None:
                row = BenchmarkSetting(organization_id=organization_id, updated_by=actor)
                session.add(row)
            row.share_anonymized_aggregates = bool(share)
            row.minimum_cohort_size = minimum
            row.updated_by = actor
            session.flush(); return row

    def capture_facility(self, *, organization_id: str, facility_id: str, days: int = 30) -> list[BenchmarkObservation]:
        period_end = date.today()
        period_start = period_end - timedelta(days=max(7, min(int(days), 365)))
        metrics: list[tuple[str, str, float, str, int]] = []

        # Extraction metrics are grouped by workflow so BHO is not benchmarked against rosin.
        extraction = ExtractionPerformanceService(self.engine)
        with self._sessions() as session:
            runs = list(session.scalars(select(ExtractionRun).where(ExtractionRun.organization_id == organization_id, ExtractionRun.facility_id == facility_id, ExtractionRun.status.notin_(("cancelled","failed")))))
        by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run in runs:
            try:
                by_workflow[run.workflow_key].append(extraction.run_metrics(organization_id, facility_id, run.id))
            except Exception:
                continue
        for workflow, rows in by_workflow.items():
            if not rows:
                continue
            cohort = f"extraction:{workflow}"
            for key, unit in (("yield_pct","pct"),("cost_per_output","usd_per_output"),("cycle_hours","hours"),("solvent_recovery_pct","pct")):
                values = [float(row.get(key) or 0) for row in rows if float(row.get(key) or 0) > 0]
                if values:
                    metrics.append((f"extraction_{key}", cohort, sum(values) / len(values), unit, len(values)))

        # Production aggregates deliberately avoid SKU/product/customer detail.
        try:
            production_rows = ProductionERPService(self.engine).queue_summary(organization_id, facility_id)
        except Exception:
            production_rows = []
        attainments = [float(row.get("Attainment %") or 0) for row in production_rows if float(row.get("Attainment %") or 0) > 0]
        cpu = [float(row.get("Cost / Unit") or 0) for row in production_rows if float(row.get("Cost / Unit") or 0) > 0]
        if attainments:
            metrics.append(("production_attainment_pct", "production:all", sum(attainments) / len(attainments), "pct", len(attainments)))
        if cpu:
            metrics.append(("production_cost_per_unit", "production:all", sum(cpu) / len(cpu), "usd_per_unit", len(cpu)))

        # Historical sales becomes a facility-level velocity metric only.
        with self._sessions() as session:
            sales = list(session.scalars(select(MigrationSalesHistory).where(MigrationSalesHistory.organization_id == organization_id, MigrationSalesHistory.facility_id == facility_id, MigrationSalesHistory.sale_date >= period_start, MigrationSalesHistory.sale_date <= period_end)))
        if sales:
            units = sum(float(row.units or 0) for row in sales)
            revenue = sum(float(row.revenue or 0) for row in sales)
            day_count = max(1, (period_end - period_start).days + 1)
            metrics.append(("sales_units_per_day", "retail:all", units / day_count, "units_per_day", len(sales)))
            if units > 0:
                metrics.append(("sales_revenue_per_unit", "retail:all", revenue / units, "usd_per_unit", len(sales)))

        captured: list[BenchmarkObservation] = []
        with self._sessions.begin() as session:
            for metric_key, cohort_key, value, unit, sample_count in metrics:
                row = session.scalar(select(BenchmarkObservation).where(BenchmarkObservation.facility_id == facility_id, BenchmarkObservation.metric_key == metric_key, BenchmarkObservation.cohort_key == cohort_key, BenchmarkObservation.period_start == period_start, BenchmarkObservation.period_end == period_end))
                if row is None:
                    row = BenchmarkObservation(organization_id=organization_id, facility_id=facility_id, metric_key=metric_key, cohort_key=cohort_key, value=float(value), unit=unit, sample_count=int(sample_count), period_start=period_start, period_end=period_end)
                    session.add(row)
                else:
                    row.value = float(value); row.unit = unit; row.sample_count = int(sample_count)
                captured.append(row)
            session.flush()
        return captured

    def network_summary(self, *, organization_id: str, facility_id: str, metric_key: str, cohort_key: str, higher_is_better: bool = True, max_age_days: int = 60) -> dict[str, Any]:
        cutoff = date.today() - timedelta(days=max_age_days)
        own_setting = self.setting(organization_id)
        minimum = int(getattr(own_setting, "minimum_cohort_size", 5) or 5)
        with self._sessions() as session:
            rows = session.execute(
                select(BenchmarkObservation, BenchmarkSetting)
                .join(BenchmarkSetting, BenchmarkSetting.organization_id == BenchmarkObservation.organization_id)
                .where(
                    BenchmarkObservation.metric_key == metric_key,
                    BenchmarkObservation.cohort_key == cohort_key,
                    BenchmarkObservation.period_end >= cutoff,
                    BenchmarkSetting.share_anonymized_aggregates.is_(True),
                )
                .order_by(BenchmarkObservation.captured_at.desc())
            ).all()
            own_rows = list(session.scalars(select(BenchmarkObservation).where(BenchmarkObservation.organization_id == organization_id, BenchmarkObservation.facility_id == facility_id, BenchmarkObservation.metric_key == metric_key, BenchmarkObservation.cohort_key == cohort_key).order_by(BenchmarkObservation.captured_at.desc()).limit(1)))

        latest_by_facility: dict[str, BenchmarkObservation] = {}
        organizations: set[str] = set()
        for observation, _setting in rows:
            if observation.facility_id not in latest_by_facility:
                latest_by_facility[observation.facility_id] = observation
                organizations.add(observation.organization_id)
        values = [float(row.value) for row in latest_by_facility.values()]
        if len(organizations) < minimum:
            return {"available": False, "cohort_organizations": len(organizations), "minimum_cohort_size": minimum, "message": f"Network benchmark unlocks at {minimum} opted-in organizations."}
        current = float(own_rows[0].value) if own_rows else None
        return {
            "available": True,
            "cohort_organizations": len(organizations),
            "facilities": len(values),
            "minimum_cohort_size": minimum,
            "median": median(values),
            "p25": _percentile(values, 0.25),
            "p75": _percentile(values, 0.75),
            "current": current,
            "percentile": _rank(current, values, higher_is_better=higher_is_better) if current is not None else None,
        }

    def facility_dashboard(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = list(session.scalars(select(BenchmarkObservation).where(BenchmarkObservation.organization_id == organization_id, BenchmarkObservation.facility_id == facility_id).order_by(BenchmarkObservation.captured_at.desc())))
        latest: dict[tuple[str, str], BenchmarkObservation] = {}
        for row in rows:
            latest.setdefault((row.metric_key, row.cohort_key), row)
        output = []
        lower_better = {"extraction_cost_per_output", "extraction_cycle_hours", "production_cost_per_unit"}
        for (metric, cohort), row in latest.items():
            network = self.network_summary(organization_id=organization_id, facility_id=facility_id, metric_key=metric, cohort_key=cohort, higher_is_better=metric not in lower_better)
            output.append({"metric_key": metric, "cohort_key": cohort, "value": float(row.value), "unit": row.unit, "sample_count": row.sample_count, "network": network})
        return output
