from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.integrations.models import IntegrationSyncAttempt, IntegrationSyncState
from services.metrc_incremental_sync import INCREMENTAL_RESOURCES
from .metrc_context import MetrcContext
from .metrc_natural_sync import MetrcNaturalSyncControlService, _expected_resources


FULL_REFRESH_INTERVAL = timedelta(hours=24)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class MetrcPolicySyncControlService(MetrcNaturalSyncControlService):
    """Use cheap deltas routinely, but periodically prove full provider membership.

    Incremental LastModified reads cannot prove that an omitted active object was
    removed and not every mirrored reference resource has a proven delta contract.
    Once per 24 hours of sync activity, the control therefore returns to a complete
    authenticated facility baseline. Permission-skipped resources remain exempt.
    """

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.engine = engine

    def _full_refresh_evidence(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
    ) -> dict[str, Any]:
        expected = set(_expected_resources())
        incremental = {name for name, _provider in INCREMENTAL_RESOURCES}
        with Session(self.engine) as session:
            states = list(session.scalars(select(IntegrationSyncState).where(
                IntegrationSyncState.organization_id == organization_id,
                IntegrationSyncState.facility_id == facility_id,
                IntegrationSyncState.provider == "metrc",
                IntegrationSyncState.environment == environment,
                IntegrationSyncState.resource.in_(tuple(expected)),
            ))) if expected else []
            attempts = list(session.scalars(select(IntegrationSyncAttempt).where(
                IntegrationSyncAttempt.organization_id == organization_id,
                IntegrationSyncAttempt.facility_id == facility_id,
                IntegrationSyncAttempt.provider == "metrc",
                IntegrationSyncAttempt.resource.in_(tuple(expected)),
                IntegrationSyncAttempt.status == "succeeded",
                IntegrationSyncAttempt.cursor_after == "initial-full",
            ))) if expected else []

        by_state = {row.resource: row for row in states}
        latest_full: dict[str, datetime] = {}
        for row in attempts:
            completed = _aware(row.completed_at)
            if completed is None:
                continue
            current = latest_full.get(row.resource)
            if current is None or completed > current:
                latest_full[row.resource] = completed

        required_full = sorted(
            name
            for name in expected
            if str(getattr(by_state.get(name), "cursor", "") or "") != "permission-skipped"
        )
        missing = [name for name in required_full if name not in latest_full]
        oldest_full = min((latest_full[name] for name in required_full if name in latest_full), default=None)
        now = datetime.now(timezone.utc)
        due_at = oldest_full + FULL_REFRESH_INTERVAL if oldest_full is not None else None
        due = bool(missing or oldest_full is None or now >= due_at)
        return {
            "due": due,
            "interval_hours": int(FULL_REFRESH_INTERVAL.total_seconds() // 3600),
            "oldest_full_baseline_at": oldest_full.isoformat() if oldest_full else None,
            "next_full_refresh_at": due_at.isoformat() if due_at else None,
            "missing_full_baseline_resources": missing,
            "incremental_resource_count": len(expected & incremental),
            "full_only_resource_count": len(expected - incremental),
        }

    def _run_full(
        self,
        *,
        organization_id: str,
        facility_id: str,
        metrc: MetrcContext,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        # The runtime composition rebinds the natural-sync module's bootstrap class
        # to the final resilient + canonical hydration implementation.
        from . import metrc_natural_sync as natural_sync_module

        full = natural_sync_module.ResilientSnapshottingMetrcFacilityBootstrapService(self.engine).sync(
            organization_id=organization_id,
            facility_id=facility_id,
            license_number=metrc.license_number,
            state=metrc.state,
            environment=metrc.environment,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            actor=actor,
        )
        failed = int(full.get("totals", {}).get("failed") or 0)
        records = int(full.get("totals", {}).get("records") or 0)
        resources = [
            {
                "resource": str(row.get("resource") or ""),
                "run_id": str(row.get("run_id") or ""),
                "status": str(row.get("status") or ""),
                "cursor_before": "",
                "cursor_after": str((row.get("hydration_checkpoint") or {}).get("status") or "initial-full"),
                "record_count": int(row.get("record_count") or 0),
                "accepted_count": int(row.get("accepted_count") or row.get("record_count") or 0),
                "duplicate_count": int(row.get("duplicate_count") or 0),
                "error_count": 1 if row.get("status") == "failed" else 0,
                "transport": str(row.get("transport") or "metrc_authenticated_full"),
            }
            for row in full.get("resources", [])
            if isinstance(row, dict)
        ]
        return {
            "provider": "metrc",
            "provider_id": "metrc",
            "environment": metrc.environment,
            "production_writes_enabled": False,
            "transport": "metrc_authenticated_full",
            "sync_mode": "full_hydration",
            "full_hydration_reason": reason,
            "authenticated_provider_data": True,
            "resources": resources,
            "totals": {
                "records": records,
                "accepted": records,
                "duplicates": sum(row["duplicate_count"] for row in resources),
                "errors": failed,
            },
            "bootstrap": full,
        }

    def sync(
        self,
        *,
        organization_id: str,
        facility_id: str,
        metrc: MetrcContext,
        actor: str,
    ) -> dict[str, Any]:
        if not metrc.configured or not metrc.trusted_mapping:
            raise ValueError(metrc.message or "Verify the exact Metrc sandbox facility mapping before synchronization.")
        baseline_ready = self.full_baseline_ready(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=metrc.environment,
        )
        if not baseline_ready:
            return self._run_full(
                organization_id=organization_id,
                facility_id=facility_id,
                metrc=metrc,
                actor=actor,
                reason="baseline_required",
            )
        evidence = self._full_refresh_evidence(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=metrc.environment,
        )
        if evidence["due"]:
            result = self._run_full(
                organization_id=organization_id,
                facility_id=facility_id,
                metrc=metrc,
                actor=actor,
                reason="periodic_membership_revalidation",
            )
            result["full_refresh_policy"] = evidence
            return result
        result = super().sync(
            organization_id=organization_id,
            facility_id=facility_id,
            metrc=metrc,
            actor=actor,
        )
        result["full_refresh_policy"] = evidence
        return result

    def status(
        self,
        *,
        organization_id: str,
        facility_id: str,
        metrc: MetrcContext,
    ) -> dict[str, Any]:
        result = super().status(
            organization_id=organization_id,
            facility_id=facility_id,
            metrc=metrc,
        )
        if metrc.configured:
            result["full_refresh_policy"] = self._full_refresh_evidence(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=metrc.environment or "sandbox",
            )
        else:
            result["full_refresh_policy"] = {
                "due": False,
                "interval_hours": int(FULL_REFRESH_INTERVAL.total_seconds() // 3600),
                "oldest_full_baseline_at": None,
                "next_full_refresh_at": None,
                "missing_full_baseline_resources": [],
            }
        return result
