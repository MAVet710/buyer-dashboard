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
CULTIVATION_RESOURCES = (
    "locations",
    "plant_batches",
    "plants_vegetative",
    "plants_flowering",
    "harvests",
)


class NaturalMetrcFacilityBootstrapService(ResilientSnapshottingMetrcFacilityBootstrapService):
    """Promote complete current provider snapshots into natural DL workspaces.

    The resilient/snapshotting parent remains the authority for provider reads,
    immutable audit history, page resume, and current-membership replacement.
    This final layer materializes only resources proven current by that run.
    Composite cultivation materialization additionally requires every cultivation
    dependency to be complete in the same provider baseline.
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

    def _current_records(self, *, organization_id: str, facility_id: str, environment: str, resource: str) -> list[dict[str, Any]]:
        rows = self.provider_snapshots.current(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            resources=(resource,),
            environment=environment,
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
        return records

    def sync(self, **kwargs) -> dict[str, Any]:
        result = super().sync(**kwargs)
        summaries = {
            str(row.get("resource") or ""): row
            for row in result.get("resources", [])
            if isinstance(row, dict)
        }
        current_resources = {
            resource
            for resource, summary in summaries.items()
            if str((summary.get("current_snapshot") or {}).get("status") or "") == "current"
        }
        cultivation_complete = all(resource in current_resources for resource in CULTIVATION_RESOURCES)

        organization_id = str(kwargs.get("organization_id") or "")
        facility_id = str(kwargs.get("facility_id") or "")
        environment = str(kwargs.get("environment") or "").strip().casefold()
        snapshots: dict[str, list[dict[str, Any]]] = {}
        for resource in HYDRATABLE_CURRENT_RESOURCES:
            if resource not in current_resources:
                continue
            # Cultivation is a composite canonical workspace. Do not create a
            # partial local lifecycle if one of its provider dependencies failed,
            # truncated, or was permission-skipped in this full baseline.
            if resource in CULTIVATION_RESOURCES and not cultivation_complete:
                continue
            snapshots[resource] = self._current_records(
                organization_id=organization_id,
                facility_id=facility_id,
                environment=environment,
                resource=resource,
            )

        workspace = MetrcWorkspaceHydrationService(self.engine).hydrate(
            organization_id=organization_id,
            facility_id=facility_id,
            state=str(kwargs.get("state") or ""),
            environment=environment,
            license_number=str(kwargs.get("license_number") or ""),
            actor=str(kwargs.get("actor") or "system"),
            resource_snapshots=snapshots,
        )
        workspace["complete_snapshot_only"] = True
        workspace.setdefault("workspace_gates", {})["cultivation"] = {
            "status": "current" if cultivation_complete else "withheld_incomplete_snapshot",
            "required_resources": list(CULTIVATION_RESOURCES),
            "current_resources": [resource for resource in CULTIVATION_RESOURCES if resource in current_resources],
            "network_request_made": False,
        }
        result["workspace_hydration"] = workspace
        return result
