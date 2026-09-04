from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.integrations.models import IntegrationSyncState
from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository


class MetrcWorkspaceSnapshotService:
    """Project current locally-synced Metrc state into operator workspaces.

    This service never contacts Metrc and never decrypts credentials. It combines
    the current provider snapshot with durable sync-state evidence so an empty
    provider collection can be distinguished from a resource that has never been
    synchronized successfully.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.snapshots = IntegrationProviderSnapshotRepository(engine)

    @staticmethod
    def _decode(raw_payload_json: str) -> dict[str, Any]:
        try:
            value = json.loads(raw_payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def read(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        resources: tuple[str, ...],
    ) -> dict[str, Any]:
        env = str(environment or "").strip().casefold()
        requested = tuple(dict.fromkeys(str(resource or "").strip().casefold() for resource in resources if str(resource or "").strip()))
        rows = self.snapshots.current(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            resources=requested,
            environment=env,
            limit=10000,
        )
        grouped: dict[str, list[Any]] = {resource: [] for resource in requested}
        for row in rows:
            grouped.setdefault(row.resource, []).append(row)

        with Session(self.engine) as session:
            states = list(
                session.scalars(
                    select(IntegrationSyncState).where(
                        IntegrationSyncState.organization_id == organization_id,
                        IntegrationSyncState.facility_id == facility_id,
                        IntegrationSyncState.provider == "metrc",
                        IntegrationSyncState.environment == env,
                        IntegrationSyncState.resource.in_(requested),
                    )
                )
            ) if requested else []
        state_by_resource = {row.resource: row for row in states}

        output: dict[str, dict[str, Any]] = {}
        for resource in requested:
            resource_rows = grouped.get(resource, [])
            state = state_by_resource.get(resource)
            cursor = str(state.cursor or "") if state is not None else ""
            permission_skipped = cursor == "permission-skipped"
            complete = bool(
                state is not None
                and state.status == "succeeded"
                and cursor == "initial-full"
                and not permission_skipped
            )
            last_synced_at = None
            if resource_rows:
                last_synced_at = max(row.last_seen_at for row in resource_rows if row.last_seen_at is not None).isoformat()
            elif state is not None and state.last_success_at is not None:
                last_synced_at = state.last_success_at.isoformat()

            output[resource] = {
                "resource": resource,
                "source": "integration_provider_snapshots",
                "network_request_made": False,
                "status": (
                    "current" if complete else
                    "permission_skipped" if permission_skipped else
                    "incomplete" if cursor == "initial-incomplete" else
                    "failed" if state is not None and state.status == "failed" else
                    "not_synced"
                ),
                "complete": complete,
                "count": len(resource_rows),
                "last_synced_at": last_synced_at,
                "records": [self._decode(row.raw_payload_json) for row in resource_rows],
            }

        completed = [row for row in output.values() if row["complete"]]
        timestamps = [row["last_synced_at"] for row in completed if row["last_synced_at"]]
        return {
            "provider": "metrc",
            "environment": env,
            "source": "integration_provider_snapshots",
            "network_request_made": False,
            "requested_resource_count": len(requested),
            "complete_resource_count": len(completed),
            "all_complete": len(completed) == len(requested) if requested else True,
            "last_synced_at": max(timestamps) if timestamps else None,
            "resources": output,
        }
