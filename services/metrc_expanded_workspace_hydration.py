from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import Engine

from services.metrc_cultivation_materialization import MetrcCultivationMaterializer
from services.metrc_workspace_hydration import MetrcWorkspaceHydrationService as BaseMetrcWorkspaceHydrationService


class MetrcWorkspaceHydrationService(BaseMetrcWorkspaceHydrationService):
    """Extend the established Product/Inventory hydrator into Cultivation.

    Existing provider-owned transfer/history objects remain shadows. Existing local
    cultivation objects remain non-overwrite; exact provider IDs and regulatory tags
    are the identity boundary for provider-seeded canonical state.
    """

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.engine = engine

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

        cultivation_keys = (
            "locations",
            "plant_batches",
            "plants_vegetative",
            "plants_flowering",
            "harvests",
        )
        if any(snapshots.get(key) for key in cultivation_keys):
            cultivation = MetrcCultivationMaterializer(self.engine).seed(
                organization_id=organization_id,
                facility_id=facility_id,
                state=state,
                environment=environment,
                license_number=license_number,
                actor=actor,
                locations=[dict(row) for row in snapshots.get("locations", []) if isinstance(row, dict)],
                plant_batches=[dict(row) for row in snapshots.get("plant_batches", []) if isinstance(row, dict)],
                vegetative_plants=[dict(row) for row in snapshots.get("plants_vegetative", []) if isinstance(row, dict)],
                flowering_plants=[dict(row) for row in snapshots.get("plants_flowering", []) if isinstance(row, dict)],
                harvests=[dict(row) for row in snapshots.get("harvests", []) if isinstance(row, dict)],
            )
            result.setdefault("workspaces", {})["cultivation"] = cultivation

        workspaces = result.get("workspaces", {})
        result["materialized_workspaces"] = sorted(
            name for name, row in workspaces.items() if isinstance(row, dict) and row.get("mode") == "materialized"
        )
        result["provider_shadow_workspaces"] = sorted(
            name for name, row in workspaces.items() if isinstance(row, dict) and row.get("mode") == "provider_shadow"
        )
        return result
