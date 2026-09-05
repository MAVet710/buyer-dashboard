from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine

from services.metrc_authoritative_inventory_membership import MetrcAuthoritativeInventoryMembershipReconciler
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

    A complete active-package snapshot also owns absence semantics: a previously
    linked package missing from that complete snapshot is closed to zero and marked
    inactive locally. Incremental LastModified sync never infers absence.
    """

    # Transfer templates are facility-scoped and can safely join the complete
    # baseline. Lab-test results are intentionally excluded here: Metrc documents
    # GET /labtests/v2/results as a package-specific lookup, so those remain exact
    # package reads instead of an invalid facility-wide call.
    NORMALIZED_RESOURCES = ResilientSnapshottingMetrcFacilityBootstrapService.NORMALIZED_RESOURCES + (
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
        state = str(kwargs.get("state") or "")
        license_number = str(kwargs.get("license_number") or "")
        actor = str(kwargs.get("actor") or "system")
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
            state=state,
            environment=environment,
            license_number=license_number,
            actor=actor,
            resource_snapshots=snapshots,
        )
        workspace["complete_snapshot_only"] = True

        if "packages" in current_resources:
            membership = MetrcAuthoritativeInventoryMembershipReconciler(self.engine).reconcile_absent(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                current_packages=snapshots.get("packages", []),
            )
            inventory = workspace.setdefault("workspaces", {}).setdefault(
                "inventory",
                {
                    "workspace": "inventory",
                    "mode": "materialized",
                    "source_package_count": len(snapshots.get("packages", [])),
                    "authority": "metrc",
                    "regulated_state_authoritative": True,
                },
            )
            inventory["complete_membership_reconciliation"] = membership
            workspace["materialized_workspaces"] = sorted(
                name
                for name, row in workspace.get("workspaces", {}).items()
                if isinstance(row, dict) and row.get("mode") == "materialized"
            )

        workspace.setdefault("workspace_gates", {})["cultivation"] = {
            "status": "current" if cultivation_complete else "withheld_incomplete_snapshot",
            "required_resources": list(CULTIVATION_RESOURCES),
            "current_resources": [resource for resource in CULTIVATION_RESOURCES if resource in current_resources],
            "network_request_made": False,
        }
        result["workspace_hydration"] = workspace
        return result
