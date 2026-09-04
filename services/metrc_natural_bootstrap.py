from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine

from services.metrc_expanded_workspace_hydration import MetrcWorkspaceHydrationService
from services.metrc_resilient_bootstrap import ResilientSnapshottingMetrcFacilityBootstrapService


HYDRATABLE_CURRENT_RESOURCES = (
    "locations",
    "items",
    "packages",
    "plant_batches",
    "plants_vegetative",
    "plants_flowering",
    "harvests",
    "incoming_transfers",
    "outgoing_transfers",
    "rejected_transfers",
)


class NaturalMetrcFacilityBootstrapService(ResilientSnapshottingMetrcFacilityBootstrapService):
    """Promote complete current provider snapshots into natural DL workspaces.

    The resilient/snapshotting parent remains the authority for provider reads,
    immutable audit history, page resume, and current-membership replacement.
    This final layer materializes only resources proven current by that run.
    """

    # These resources already have a verified read contract but do not belong to
    # the earlier core bootstrap. Mirror them during each complete baseline so
    # compliance/testing and transfer-control views are not dependent on a live
    # provider request just to discover existing regulatory state.
    NORMALIZED_RESOURCES = ResilientSnapshottingMetrcFacilityBootstrapService.NORMALIZED_RESOURCES + (
        ("lab_results", "lab_results"),
        ("transfer_templates_outgoing", "transfer_templates_outgoing"),
    )

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.engine = engine

    def sync(self, **kwargs) -> dict[str, Any]:
        result = super().sync(**kwargs)
        summaries = {
            str(row.get("resource") or ""): row
            for row in result.get("resources", [])
            if isinstance(row, dict)
        }
        snapshots: dict[str, list[dict[str, Any]]] = {}
        for resource in HYDRATABLE_CURRENT_RESOURCES:
            summary = summaries.get(resource) or {}
            if str((summary.get("current_snapshot") or {}).get("status") or "") != "current":
                continue
            rows = self.provider_snapshots.current(
                organization_id=str(kwargs.get("organization_id") or ""),
                facility_id=str(kwargs.get("facility_id") or ""),
                provider="metrc",
                resources=(resource,),
                environment=str(kwargs.get("environment") or "").strip().casefold(),
                limit=10000,
            )
            records: list[dict[str, Any]] = []
            for row in rows:
                try:
                    payload = json.loads(row.raw_payload_json or "{}")
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
            snapshots[resource] = records

        result["workspace_hydration"] = MetrcWorkspaceHydrationService(self.engine).hydrate(
            organization_id=str(kwargs.get("organization_id") or ""),
            facility_id=str(kwargs.get("facility_id") or ""),
            state=str(kwargs.get("state") or ""),
            environment=str(kwargs.get("environment") or ""),
            license_number=str(kwargs.get("license_number") or ""),
            actor=str(kwargs.get("actor") or "system"),
            resource_snapshots=snapshots,
        )
        result["workspace_hydration"]["complete_snapshot_only"] = True
        return result
