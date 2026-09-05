from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine

from services.metrc_authoritative_inventory_membership import MetrcAuthoritativeInventoryMembershipReconciler
from services.metrc_expanded_workspace_hydration import MetrcWorkspaceHydrationService
from services.metrc_projection_registry import missing_projection_resources, projection_for_resource
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
    """Promote verified provider snapshots into natural DoobieLogic workspaces.

    The resilient/snapshotting parent owns provider reads, immutable audit history,
    page resume, and current-membership replacement. This layer projects each
    independently verified resource into native DoobieLogic state without making an
    unrelated restricted resource a prerequisite for visibility.

    A complete active-package snapshot owns package absence semantics. Cultivation
    active collections deliberately do not infer terminal lifecycle state from
    absence. Incremental LastModified sync never infers deletion from omission.
    """

    # Transfer templates are facility-scoped and can safely join the complete
    # baseline. Lab-test results are intentionally excluded here because the Metrc
    # result endpoint is package-specific and must remain an exact package lookup.
    NORMALIZED_RESOURCES = ResilientSnapshottingMetrcFacilityBootstrapService.NORMALIZED_RESOURCES + (
        ("transfer_templates_outgoing", "transfer_templates_outgoing"),
    )

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.engine = engine

    def _current_records(
        self,
        *,
        organization_id: str,
        facility_id: str,
        environment: str,
        resource: str,
    ) -> list[dict[str, Any]]:
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
        cultivation_current = [resource for resource in CULTIVATION_RESOURCES if resource in current_resources]
        cultivation_complete = len(cultivation_current) == len(CULTIVATION_RESOURCES)

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
            # Independently verified resources are allowed to project. The expanded
            # hydrator resolves unchanged cultivation dependencies from the local
            # provider mirror and never makes a live Metrc request from workspace
            # hydration. Missing identity still fails closed at the object boundary.
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
        workspace["complete_snapshot_only"] = False
        workspace["verified_resource_only"] = True

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

        if cultivation_complete:
            cultivation_status = "current"
        elif cultivation_current:
            cultivation_status = "partial_current"
        else:
            cultivation_status = "unavailable_or_not_synced"
        workspace.setdefault("workspace_gates", {})["cultivation"] = {
            "status": cultivation_status,
            "required_resources_for_complete_baseline": list(CULTIVATION_RESOURCES),
            "current_resources": cultivation_current,
            "missing_or_restricted_resources": [
                resource for resource in CULTIVATION_RESOURCES if resource not in current_resources
            ],
            "independently_verified_resources_project": True,
            "unrelated_resource_failure_blocks_projection": False,
            "network_request_made": False,
        }

        projection_contract: dict[str, dict[str, object]] = {}
        for resource in summaries:
            spec = projection_for_resource(resource)
            if spec is not None:
                projection_contract[resource] = spec.public()
        runtime_resources = {
            name for name, _provider_resource in self.NORMALIZED_RESOURCES
        } | {
            name for name, _path, _paginated in self.DIRECT_RESOURCES
        }
        unmapped = missing_projection_resources(runtime_resources)
        workspace["projection_contract"] = projection_contract
        workspace["projection_integrity"] = {
            "zero_orphan_contract": not unmapped,
            "unmapped_resources": list(unmapped),
            "runtime_resource_count": len(runtime_resources),
            "declared_projection_count": len(runtime_resources) - len(unmapped),
        }
        result["workspace_hydration"] = workspace
        return result
