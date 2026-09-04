from __future__ import annotations

from typing import Any

from modules.coman.models import Facility
from services.metrc_workspace_hydration import MetrcWorkspaceHydrationService

from .sandbox_runtime import ADAPTERS, PROVIDER_IDS, SandboxIntegrationRuntime as BaseSandboxIntegrationRuntime


class NaturalSandboxIntegrationRuntime(BaseSandboxIntegrationRuntime):
    """Sandbox runtime that makes successful Metrc reads visible where operators work.

    The legacy sandbox adapter is still a deterministic fixture. After the durable
    provider-sync ledger succeeds, the exact same fixture snapshot is routed through
    the production-shaped Metrc workspace hydration service. This keeps the DEV
    acceptance path honest: items appear in Product Master, packages appear in
    Inventory, and transfers remain provider-owned state for Transfer Control.

    Production writes remain disabled. This class does not turn fixture records into
    Metrc writes or fabricate local manifest/receiving actions.
    """

    def sync(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        actor: str,
        resource: str = "",
    ) -> dict[str, Any]:
        result = super().sync(
            organization_id=organization_id,
            facility_id=facility_id,
            provider=provider,
            actor=actor,
            resource=resource,
        )
        if str(provider or "").strip().casefold() != "metrc" or result.get("totals", {}).get("errors"):
            return result

        row = self.configurations.get(
            "facility",
            self.scope_key(organization_id, facility_id),
            PROVIDER_IDS["metrc"],
        )
        configuration = self.configurations.public(row).get("configuration") or {}
        if str(configuration.get("environment") or "").casefold() != "sandbox":
            return result

        resources = (resource.strip().casefold(),) if resource.strip() else ADAPTERS["metrc"].resources
        scope_seed = f"{organization_id}:{facility_id}"
        snapshots: dict[str, list[dict[str, Any]]] = {}
        for name in resources:
            records = ADAPTERS["metrc"].fixture_records(
                resource=name,
                configuration=configuration,
                scope_seed=scope_seed,
            )
            snapshots[name] = self._enrich_metrc_fixture(name, records, scope_seed)

        with self.sessions() as session:
            facility = session.get(Facility, facility_id)
            local_license = str(facility.license_number or "").strip() if facility is not None else ""
        state = str(configuration.get("state") or "MA").strip().upper() or "MA"
        license_number = str(configuration.get("license_number") or local_license or "SANDBOX").strip()

        result["workspace_hydration"] = MetrcWorkspaceHydrationService(self.engine).hydrate(
            organization_id=organization_id,
            facility_id=facility_id,
            state=state,
            environment="sandbox",
            license_number=license_number,
            actor=actor,
            resource_snapshots=snapshots,
        )
        return result

    @staticmethod
    def _enrich_metrc_fixture(
        resource: str,
        records: list[dict[str, Any]],
        scope_seed: str,
    ) -> list[dict[str, Any]]:
        """Give deterministic fixtures the same identity shape as real Metrc reads."""

        if resource == "items":
            enriched: list[dict[str, Any]] = []
            for record in records:
                row = dict(record)
                item_id = str(row.get("id") or "").strip()
                name = str(row.get("name") or "").strip()
                category = str(row.get("category") or "").strip()
                row.update(
                    {
                        "provider_id": item_id,
                        "Id": item_id,
                        "Name": name,
                        "ProductCategoryName": category,
                        "UnitOfMeasureName": "g",
                    }
                )
                enriched.append(row)
            return enriched

        if resource == "packages":
            item_rows = ADAPTERS["metrc"].fixture_records(
                resource="items",
                configuration={"state": records[0].get("state", "MA") if records else "MA"},
                scope_seed=scope_seed,
            )
            enriched = []
            for index, record in enumerate(records):
                row = dict(record)
                package_id = str(row.get("id") or "").strip()
                label = str(row.get("label") or "").strip()
                item_record = item_rows[index] if index < len(item_rows) else {}
                item_id = str(item_record.get("id") or "").strip()
                item_name = str(row.get("item") or item_record.get("name") or "").strip()
                category = str(item_record.get("category") or "").strip()
                row.update(
                    {
                        "provider_id": package_id,
                        "Id": package_id,
                        "Label": label,
                        "ItemId": item_id,
                        "ItemName": item_name,
                        "ItemCategoryName": category,
                        "Item": {
                            "Id": item_id,
                            "Name": item_name,
                            "ProductCategoryName": category,
                            "UnitOfMeasureName": "g",
                        },
                        "Quantity": float(row.get("quantity") or 0),
                        "UnitOfMeasureName": "g",
                        "LabTestingState": "NotRequired",
                    }
                )
                enriched.append(row)
            return enriched

        return [dict(record) for record in records]
