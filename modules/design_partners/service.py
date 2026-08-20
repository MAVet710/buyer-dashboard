"""Design-partner pilot and case-study measurement service."""

from __future__ import annotations

from datetime import date
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Organization, utc_now

from .models import DesignPartnerAccount, DesignPartnerFeedback, DesignPartnerMetric


DEFAULT_SUCCESS_TARGETS = {
    "hours_saved_per_week": 5.0,
    "reconciliation_errors_avoided": 10.0,
    "inventory_accuracy_pct": 98.0,
    "cogs_coverage_pct": 90.0,
    "yield_improvement_pct": 3.0,
}


class DesignPartnerService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def enroll(
        self,
        *,
        organization_id: str,
        actor: str,
        champion_name: str = "",
        champion_email: str = "",
        pain_profile: str = "",
        success_targets: dict[str, float] | None = None,
        target_case_study_date: date | None = None,
        notes: str = "",
    ) -> DesignPartnerAccount:
        with self._sessions.begin() as session:
            if not session.get(Organization, organization_id):
                raise ValueError("Organization was not found.")
            row = session.scalar(select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id))
            if row is None:
                row = DesignPartnerAccount(
                    organization_id=organization_id,
                    status="pilot",
                    updated_by=actor,
                )
                session.add(row)
            elif row.status == "prospect":
                row.status = "pilot"
            row.champion_name = str(champion_name or row.champion_name or "")
            row.champion_email = str(champion_email or row.champion_email or "")
            row.pain_profile = str(pain_profile or row.pain_profile or "")
            row.success_targets_json = json.dumps(success_targets or json.loads(row.success_targets_json or "{}") or DEFAULT_SUCCESS_TARGETS, sort_keys=True)
            row.started_at = row.started_at or date.today()
            row.target_case_study_date = target_case_study_date or row.target_case_study_date
            row.notes = str(notes or row.notes or "")
            row.updated_by = actor
            session.flush(); return row

    def account(self, organization_id: str) -> DesignPartnerAccount | None:
        with self._sessions() as session:
            return session.scalar(select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id))

    def set_status(self, *, organization_id: str, status: str, actor: str) -> DesignPartnerAccount:
        allowed = {"prospect","pilot","live","case_study","graduated","churned"}
        status = str(status or "").strip().casefold()
        if status not in allowed:
            raise ValueError("Unsupported design-partner status.")
        with self._sessions.begin() as session:
            row = session.scalar(select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id))
            if row is None:
                raise ValueError("Enroll the organization before changing pilot status.")
            row.status = status
            row.updated_by = actor
            return row

    def upsert_metric(
        self,
        *,
        organization_id: str,
        metric_key: str,
        baseline_value: float,
        current_value: float,
        unit: str,
        actor: str,
        direction: str = "higher",
        evidence: str = "",
    ) -> DesignPartnerMetric:
        direction = str(direction or "higher").strip().casefold()
        if direction not in {"higher","lower"}:
            raise ValueError("Metric direction must be higher or lower.")
        with self._sessions.begin() as session:
            account = session.scalar(select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id))
            if account is None:
                raise ValueError("Enroll the organization before recording pilot metrics.")
            row = session.scalar(select(DesignPartnerMetric).where(DesignPartnerMetric.account_id == account.id, DesignPartnerMetric.metric_key == metric_key))
            if row is None:
                row = DesignPartnerMetric(organization_id=organization_id, account_id=account.id, metric_key=str(metric_key), updated_by=actor)
                session.add(row)
            row.baseline_value = float(baseline_value)
            row.current_value = float(current_value)
            row.unit = str(unit or "")
            row.direction = direction
            row.evidence = str(evidence or "")
            row.updated_by = actor
            session.flush(); return row

    def add_feedback(self, *, organization_id: str, area: str, feedback: str, actor: str, severity: str = "medium") -> DesignPartnerFeedback:
        if not str(feedback or "").strip():
            raise ValueError("Feedback is required.")
        with self._sessions.begin() as session:
            account = session.scalar(select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id))
            if account is None:
                raise ValueError("Enroll the organization before recording pilot feedback.")
            row = DesignPartnerFeedback(organization_id=organization_id, account_id=account.id, area=str(area or "General"), severity=str(severity or "medium").casefold(), feedback=str(feedback).strip(), status="open", submitted_by=actor)
            session.add(row); session.flush(); return row

    def resolve_feedback(self, *, organization_id: str, feedback_id: str, status: str, actor: str) -> DesignPartnerFeedback:
        if status not in {"planned","shipped","declined"}:
            raise ValueError("Unsupported feedback resolution status.")
        with self._sessions.begin() as session:
            row = session.get(DesignPartnerFeedback, feedback_id)
            if not row or row.organization_id != organization_id:
                raise ValueError("Feedback was not found for this organization.")
            row.status = status
            row.resolved_by = actor
            row.resolved_at = utc_now()
            return row

    def snapshot(self, organization_id: str) -> dict[str, Any]:
        with self._sessions() as session:
            account = session.scalar(select(DesignPartnerAccount).where(DesignPartnerAccount.organization_id == organization_id))
            if account is None:
                return {"account": None, "metrics": [], "feedback": [], "readiness": self._readiness(None, [])}
            metrics = list(session.scalars(select(DesignPartnerMetric).where(DesignPartnerMetric.account_id == account.id).order_by(DesignPartnerMetric.metric_key)))
            feedback = list(session.scalars(select(DesignPartnerFeedback).where(DesignPartnerFeedback.account_id == account.id).order_by(DesignPartnerFeedback.created_at.desc())))
            return {"account": account, "metrics": metrics, "feedback": feedback, "readiness": self._readiness(account, metrics)}

    @staticmethod
    def _readiness(account: DesignPartnerAccount | None, metrics: list[DesignPartnerMetric]) -> dict[str, Any]:
        if account is None:
            return {"ready": False, "score": 0, "wins": [], "missing": ["pilot enrollment"]}
        targets = json.loads(account.success_targets_json or "{}")
        metric_by_key = {row.metric_key: row for row in metrics}
        wins, missing = [], []
        for key, target in targets.items():
            row = metric_by_key.get(key)
            if row is None:
                missing.append(key)
                continue
            baseline, current = float(row.baseline_value), float(row.current_value)
            improvement = (current - baseline) if row.direction == "higher" else (baseline - current)
            passed = current >= float(target) if row.direction == "higher" and key.endswith("_pct") else improvement >= float(target)
            if passed:
                wins.append({"metric": key, "baseline": baseline, "current": current, "unit": row.unit, "improvement": improvement})
            else:
                missing.append(key)
        required = max(1, len(targets))
        score = round(len(wins) / required * 100)
        return {"ready": score >= 60 and len(wins) >= 2, "score": score, "wins": wins, "missing": missing}
