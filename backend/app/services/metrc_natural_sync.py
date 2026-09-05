from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from modules.integrations.models import IntegrationSyncAttempt, IntegrationSyncState
from services.metrc_capability_matrix import (
    classify_metrc_resources,
    metrc_operator_summary,
    summarize_metrc_modules,
)
from services.metrc_incremental_sync import MetrcIncrementalSyncService
from services.metrc_resilient_bootstrap import ResilientSnapshottingMetrcFacilityBootstrapService
from .metrc_context import MetrcContext


_ACCEPTED_BASELINE_CURSORS = ("initial-full", "permission-skipped", "incremental:")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _expected_resources() -> tuple[str, ...]:
    service = ResilientSnapshottingMetrcFacilityBootstrapService
    names = {
        *(local for local, _provider in service.NORMALIZED_RESOURCES),
        *(local for local, _path, _paginated in service.DIRECT_RESOURCES),
    }
    return tuple(sorted(names))


def _baseline_cursor_ready(cursor: str) -> bool:
    value = str(cursor or "")
    return any(value.startswith(prefix) for prefix in _ACCEPTED_BASELINE_CURSORS)


class MetrcNaturalSyncControlService:
    """One meaning for the operator's Metrc Sandbox sync button.

    Before full facility hydration has completed, sync performs authenticated full
    hydration. Once every configured bootstrap resource has a completed or
    permission-skipped baseline, the same action becomes a LastModified delta sync.
    The deterministic fixture runtime is intentionally not used for a Metrc provider
    connection because it would make "sync succeeded" mean two different things.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def _states(self, *, organization_id: str, facility_id: str, environment: str) -> list[IntegrationSyncState]:
        with Session(self.engine) as session:
            return list(session.scalars(
                select(IntegrationSyncState).where(
                    IntegrationSyncState.organization_id == organization_id,
                    IntegrationSyncState.facility_id == facility_id,
                    IntegrationSyncState.provider == "metrc",
                    IntegrationSyncState.environment == environment,
                ).order_by(IntegrationSyncState.resource)
            ))

    def full_baseline_ready(self, *, organization_id: str, facility_id: str, environment: str) -> bool:
        expected = set(_expected_resources())
        states = {row.resource: row for row in self._states(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=environment,
        )}
        return bool(expected) and all(
            name in states and states[name].status == "succeeded" and _baseline_cursor_ready(states[name].cursor)
            for name in expected
        )

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
            full = ResilientSnapshottingMetrcFacilityBootstrapService(self.engine).sync(
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

        delta = MetrcIncrementalSyncService(self.engine).sync(
            organization_id=organization_id,
            facility_id=facility_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
            actor=actor,
        )
        resources = [
            {
                "resource": str(row.get("resource") or ""),
                "run_id": "",
                "status": str(row.get("status") or ""),
                "cursor_before": str(row.get("last_modified_start") or ""),
                "cursor_after": "incremental",
                "record_count": int(row.get("record_count") or 0),
                "accepted_count": int(row.get("record_count") or 0) if row.get("status") == "succeeded" else 0,
                "duplicate_count": int((row.get("current_snapshot") or {}).get("duplicates") or 0),
                "error_count": 1 if row.get("status") == "failed" else 0,
                "transport": "metrc_last_modified_delta",
            }
            for row in delta.get("resources", [])
            if isinstance(row, dict)
        ]
        return {
            "provider": "metrc",
            "provider_id": "metrc",
            "environment": metrc.environment,
            "production_writes_enabled": False,
            "transport": "metrc_last_modified_delta",
            "sync_mode": "incremental",
            "authenticated_provider_data": True,
            "resources": resources,
            "totals": {
                "records": int(delta.get("totals", {}).get("records") or 0),
                "accepted": int(delta.get("totals", {}).get("records") or 0),
                "duplicates": sum(row["duplicate_count"] for row in resources),
                "errors": int(delta.get("totals", {}).get("failed") or 0),
            },
            "incremental": delta,
        }

    def status(
        self,
        *,
        organization_id: str,
        facility_id: str,
        metrc: MetrcContext,
    ) -> dict[str, Any]:
        expected = _expected_resources()
        states = self._states(
            organization_id=organization_id,
            facility_id=facility_id,
            environment=metrc.environment or "sandbox",
        )
        by_resource = {row.resource: row for row in states}
        with Session(self.engine) as session:
            attempts = list(session.scalars(
                select(IntegrationSyncAttempt).where(
                    IntegrationSyncAttempt.organization_id == organization_id,
                    IntegrationSyncAttempt.facility_id == facility_id,
                    IntegrationSyncAttempt.provider == "metrc",
                ).order_by(desc(IntegrationSyncAttempt.started_at)).limit(20)
            ))
        rendered = []
        for resource in expected:
            row = by_resource.get(resource)
            rendered.append({
                "resource": resource,
                "status": row.status if row is not None else "idle",
                "cursor": row.cursor if row is not None else "",
                "last_started_at": _iso(row.last_started_at) if row is not None else None,
                "last_completed_at": _iso(row.last_completed_at) if row is not None else None,
                "last_success_at": _iso(row.last_success_at) if row is not None else None,
                "last_error": row.last_error if row is not None else "",
                "records_seen": int(row.records_seen or 0) if row is not None else 0,
                "records_written": int(row.records_written or 0) if row is not None else 0,
            })

        authenticated_provider_data = bool(metrc.configured and metrc.trusted_mapping)
        resource_capabilities = classify_metrc_resources(
            rendered,
            authenticated_facility_access=authenticated_provider_data,
        )
        module_health = summarize_metrc_modules(resource_capabilities)
        operator_summary = metrc_operator_summary(resource_capabilities, module_health)

        return {
            "provider": "metrc",
            "provider_id": "metrc",
            "environment": metrc.environment or "sandbox",
            "resources": list(expected),
            "configured_resources": list(expected),
            "read_mode": "authenticated_metrc_regulatory_snapshot",
            "production_writes_enabled": False,
            "adapter_contract_ready": True,
            "authenticated_provider_data": authenticated_provider_data,
            "trusted_mapping": bool(metrc.trusted_mapping),
            "license_number": metrc.license_number,
            "full_baseline_ready": self.full_baseline_ready(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=metrc.environment or "sandbox",
            ) if metrc.configured else False,
            "message": metrc.message,
            "operator_summary": operator_summary,
            "resource_capabilities": resource_capabilities,
            "module_health": module_health,
            "states": rendered,
            "recent_attempts": [{
                "run_id": row.run_id,
                "resource": row.resource,
                "status": row.status,
                "record_count": int(row.record_count or 0),
                "accepted_count": int(row.accepted_count or 0),
                "duplicate_count": int(row.duplicate_count or 0),
                "error_count": int(row.error_count or 0),
                "error_message": row.error_message,
                "started_at": _iso(row.started_at),
                "completed_at": _iso(row.completed_at),
            } for row in attempts],
        }
