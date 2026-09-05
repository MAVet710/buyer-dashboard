from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import Engine

from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository
from services.metrc_authoritative_cultivation import MetrcAuthoritativeCultivationReconciler
from services.metrc_authoritative_inventory import MetrcAuthoritativeInventoryReconciler
from services.metrc_cultivation_materialization import MetrcCultivationMaterializer
from services.metrc_workspace_hydration import MetrcWorkspaceHydrationService as BaseMetrcWorkspaceHydrationService


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("source")
    return nested if isinstance(nested, Mapping) else record


def _explicit_batch_strain(record: Mapping[str, Any]) -> str:
    source = _source(record)
    value = source.get("StrainName") or source.get("strainName") or source.get("Strain") or source.get("strain")
    if isinstance(value, Mapping):
        value = value.get("Name") or value.get("name")
    return str(value or "").strip()


def _provider_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    return str(record.get("provider_id") or source.get("Id") or source.get("ID") or source.get("id") or "").strip()


def _referenced_location_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    nested = source.get("Location") or source.get("location") or source.get("DryingLocation") or source.get("dryingLocation")
    nested_id = ""
    if isinstance(nested, Mapping):
        nested_id = str(nested.get("Id") or nested.get("id") or "").strip()
    return str(
        source.get("LocationId")
        or source.get("locationId")
        or source.get("CurrentLocationId")
        or source.get("currentLocationId")
        or source.get("DryingLocationId")
        or source.get("dryingLocationId")
        or source.get("HarvestLocationId")
        or source.get("harvestLocationId")
        or nested_id
        or ""
    ).strip()


class MetrcWorkspaceHydrationService(BaseMetrcWorkspaceHydrationService):
    """Extend provider hydration into canonical Inventory and Cultivation workspaces.

    Metrc is authoritative for the regulated package and cultivation fields it
    explicitly reports. The base hydrator establishes exact provider identity and
    seeds new canonical rows; this layer then reconciles already-linked objects to
    provider truth while preserving local ERP enrichment and append-only evidence.
    Provider-owned transfer/history objects remain shadows. Identity is always exact
    and fail-closed; no mutable-name rebinding is allowed.
    """

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.engine = engine
        self.provider_snapshots = IntegrationProviderSnapshotRepository(engine)

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
                value = json.loads(row.raw_payload_json or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    def hydrate(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        actor: str,
        resource_snapshots: Mapping[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        snapshots = {key: list(value or []) for key, value in resource_snapshots.items()}
        transfers: list[dict[str, Any]] = []
        for key in ("transfers", "incoming_transfers", "outgoing_transfers", "rejected_transfers"):
            transfers.extend(dict(row) for row in snapshots.get(key, []) if isinstance(row, dict))
        if transfers:
            snapshots["transfers"] = transfers

        result = super().hydrate(
            organization_id=organization_id,
            facility_id=facility_id,
            state=state,
            environment=environment,
            license_number=license_number,
            actor=actor,
            resource_snapshots=snapshots,
        )

        packages = [dict(row) for row in snapshots.get("packages", []) if isinstance(row, dict)]
        if packages:
            authoritative = MetrcAuthoritativeInventoryReconciler(self.engine).reconcile(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                packages=packages,
            )
            inventory = result.setdefault("workspaces", {}).setdefault(
                "inventory",
                {
                    "workspace": "inventory",
                    "mode": "materialized",
                    "source_package_count": len(packages),
                },
            )
            inventory["authority"] = "metrc"
            inventory["regulated_state_authoritative"] = True
            inventory["authoritative_reconciliation"] = authoritative

        cultivation_keys = (
            "locations",
            "plant_batches",
            "plants_vegetative",
            "plants_flowering",
            "harvests",
        )
        cultivation_requested = any(snapshots.get(key) for key in cultivation_keys)
        if cultivation_requested:
            # A changed plant/harvest may reference an unchanged location or plant
            # batch. Resolve those dependencies from the current local provider
            # mirror; never make an extra Metrc call from workspace hydration.
            if not snapshots.get("locations"):
                snapshots["locations"] = self._current_records(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="locations",
                )
            if not snapshots.get("plant_batches") and (
                snapshots.get("plants_vegetative") or snapshots.get("plants_flowering")
            ):
                snapshots["plant_batches"] = self._current_records(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="plant_batches",
                )

            location_rows = [dict(row) for row in snapshots.get("locations", []) if isinstance(row, dict)]
            all_batches = [dict(row) for row in snapshots.get("plant_batches", []) if isinstance(row, dict)]
            valid_batches = [row for row in all_batches if _explicit_batch_strain(row)]
            invalid_batches = [row for row in all_batches if not _explicit_batch_strain(row)]
            vegetative_rows = [dict(row) for row in snapshots.get("plants_vegetative", []) if isinstance(row, dict)]
            flowering_rows = [dict(row) for row in snapshots.get("plants_flowering", []) if isinstance(row, dict)]
            harvest_rows = [dict(row) for row in snapshots.get("harvests", []) if isinstance(row, dict)]

            cultivation = MetrcCultivationMaterializer(self.engine).seed(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                locations=location_rows,
                plant_batches=valid_batches,
                vegetative_plants=vegetative_rows,
                flowering_plants=flowering_rows,
                harvests=harvest_rows,
            )
            if invalid_batches:
                rejected = [
                    {
                        "code": "plant_batch_missing_explicit_strain",
                        "provider_id": str(row.get("provider_id") or _source(row).get("Id") or ""),
                        "message": "Metrc plant batch did not provide an explicit strain identity; DoobieLogic did not infer strain from the mutable batch name.",
                    }
                    for row in invalid_batches
                ]
                cultivation.setdefault("conflicts", []).extend(rejected)
                cultivation["conflict_count"] = int(cultivation.get("conflict_count") or 0) + len(rejected)
                cultivation.setdefault("source_counts", {})["plant_batches"] = len(all_batches)

            referenced_location_ids = {
                location_id
                for row in [*valid_batches, *vegetative_rows, *flowering_rows, *harvest_rows]
                for location_id in [_referenced_location_id(row)]
                if location_id
            }
            authority_locations = [
                row for row in location_rows if _provider_id(row) in referenced_location_ids
            ]
            authoritative = MetrcAuthoritativeCultivationReconciler(self.engine).reconcile(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                locations=authority_locations,
                plant_batches=valid_batches,
                vegetative_plants=vegetative_rows,
                flowering_plants=flowering_rows,
                harvests=harvest_rows,
            )
            cultivation["authority"] = "metrc"
            cultivation["regulated_state_authoritative"] = True
            cultivation["authoritative_reconciliation"] = authoritative
            cultivation["dependency_source"] = "integration_provider_snapshots"
            cultivation["dependency_network_request_made"] = False
            result.setdefault("workspaces", {})["cultivation"] = cultivation

        workspaces = result.get("workspaces", {})
        result["materialized_workspaces"] = sorted(
            name for name, row in workspaces.items() if isinstance(row, dict) and row.get("mode") == "materialized"
        )
        result["provider_shadow_workspaces"] = sorted(
            name for name, row in workspaces.items() if isinstance(row, dict) and row.get("mode") == "provider_shadow"
        )
        return result
