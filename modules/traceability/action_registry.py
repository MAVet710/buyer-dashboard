"""Canonical domain-first registry for regulated provider actions.

The registry describes operator intent and safety policy.  Provider payload
builders remain in the reviewed Metrc adapters; registry membership alone never
grants permission to dispatch a write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.regulatory import get_metrc_write_contract


OPERATOR_ROLES = frozenset({"dev", "admin", "supervisor", "operator", "qa"})
SUPERVISOR_ROLES = frozenset({"dev", "admin", "supervisor", "qa"})


@dataclass(frozen=True)
class TraceabilityActionDefinition:
    name: str
    label: str
    entity_type: str
    required_fields: tuple[str, ...]
    roles: frozenset[str]
    provider_operation: str
    verification_resource: str
    execution_path: str = "locked"
    action_class: str = "compliance"
    supports_bulk: bool = False
    idempotency_policy: str = "exact_intent"
    retry_policy: str = "reconcile_before_retry"
    reconciliation_strategy: str = "exact_provider_readback"
    catalog_visible: bool = True

    def public(self, *, jurisdiction: str = "", environment: str = "") -> dict[str, Any]:
        contract = get_metrc_write_contract(self.provider_operation)
        dispatch_enabled = bool(
            self.execution_path == "shared_dispatch"
            and contract
            and contract.public(jurisdiction=jurisdiction, environment=environment)["dispatch_enabled"]
        )
        return {
            "operation_type": self.name,
            "operator_label": self.label,
            "entity_type": self.entity_type,
            "required_fields": list(self.required_fields),
            "roles": sorted(self.roles),
            "action_class": self.action_class,
            "provider_operation": self.provider_operation,
            "verification_resource": self.verification_resource,
            "execution_path": self.execution_path,
            "dispatch_enabled": dispatch_enabled,
            "operator_execution_enabled": self.execution_path != "locked",
            "supports_bulk": self.supports_bulk,
            "idempotency_policy": self.idempotency_policy,
            "retry_policy": self.retry_policy,
            "reconciliation_strategy": self.reconciliation_strategy,
            "preview_required": True,
            "catalog_visible": self.catalog_visible,
        }


def _action(
    name: str,
    label: str,
    entity_type: str,
    required: tuple[str, ...],
    provider_operation: str,
    verification_resource: str,
    *,
    roles: frozenset[str] = OPERATOR_ROLES,
    execution_path: str = "locked",
    supports_bulk: bool = False,
    action_class: str = "hybrid",
    catalog_visible: bool = True,
) -> TraceabilityActionDefinition:
    return TraceabilityActionDefinition(
        name=name,
        label=label,
        entity_type=entity_type,
        required_fields=required,
        roles=roles,
        provider_operation=provider_operation,
        verification_resource=verification_resource,
        execution_path=execution_path,
        supports_bulk=supports_bulk,
        action_class=action_class,
        catalog_visible=catalog_visible,
    )


TRACEABILITY_ACTIONS = {
    row.name: row
    for row in (
        _action("location_create", "Create room", "location", ("name", "location_type_name"), "location_create", "locations_by_id", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", catalog_visible=False),
        _action("location_update", "Update room", "location", ("id", "name", "location_type_name"), "location_update", "locations_by_id", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", catalog_visible=False),
        _action("strain_create", "Create strain", "strain", ("name",), "strain_create", "strains_by_id", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", catalog_visible=False),
        _action("strain_update", "Update strain", "strain", ("id", "name"), "strain_update", "strains_by_id", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", catalog_visible=False),
        _action("item_create", "Create item", "item", ("name", "item_category"), "item_create", "items_by_id", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", catalog_visible=False),
        _action("item_update", "Update item", "item", ("id", "name", "item_category"), "item_update", "items_by_id", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", catalog_visible=False),
        _action("package_create", "Create package", "package", ("source_ids", "quantity", "unit"), "package_create", "packages_active", execution_path="specialized_verified", supports_bulk=True),
        _action("package_move", "Move package", "package", ("destination_location",), "package_move", "packages_active", supports_bulk=True),
        _action("package_finish", "Finish package", "package", (), "package_finish", "packages_active", execution_path="shared_dispatch", supports_bulk=True),
        _action("package_unfinish", "Reopen package", "package", (), "package_unfinish", "packages_active", execution_path="specialized_verified"),
        _action("package_adjust", "Adjust inventory", "package", ("quantity_delta", "unit", "reason"), "package_adjust", "packages_active", execution_path="shared_dispatch", supports_bulk=True),
        _action("package_item_update", "Correct package item", "package", ("item",), "package_item_update", "packages_active", roles=SUPERVISOR_ROLES, execution_path="specialized_verified"),
        _action("package_note_update", "Update package note", "package", ("note",), "package_note_update", "packages_active"),
        _action("package_split", "Repackage inventory", "package", ("quantity", "unit"), "package_create", "packages_active", execution_path="specialized_verified", supports_bulk=True),
        _action("package_merge", "Combine packages", "package", ("source_ids",), "package_create", "packages_active", roles=SUPERVISOR_ROLES, execution_path="specialized_verified", supports_bulk=True),
        _action("plant_batch_create", "Create plant batch", "plant_batch", ("count", "strain", "actual_date"), "plant_batch_plantings", "plant_batches_active", execution_path="specialized_verified", supports_bulk=True, catalog_visible=False),
        _action("plant_batch_sync", "Create plant batch", "cultivation_group", (), "plant_batch_plantings", "plant_batches_by_id", execution_path="specialized_verified", supports_bulk=True, catalog_visible=False),
        _action("plant_batch_move", "Move plant batch", "plant_batch", ("destination_location",), "plant_batch_location_update", "plant_batches_active", supports_bulk=True),
        _action("plant_batch_vegetative", "Create plants from batch", "plant_batch", ("count", "starting_tag", "destination_location", "actual_date"), "plant_batch_growthphase", "plants_vegetative", execution_path="specialized_verified", supports_bulk=True, catalog_visible=False),
        _action("plant_move", "Move plants", "plant", ("destination_location",), "plant_location_update", "plants_by_id", execution_path="specialized_verified", supports_bulk=True),
        _action("plant_harvest", "Harvest plants", "harvest", ("plant_ids", "harvest_name"), "plant_harvest", "harvests_by_id", execution_path="specialized_verified", supports_bulk=True),
        _action("harvest_start", "Harvest plants", "cultivation_harvest", (), "plant_harvest", "harvests_by_id", execution_path="specialized_verified", supports_bulk=True, catalog_visible=False),
        _action("plant_waste", "Record plant waste", "plant", ("plant_ids", "quantity", "unit", "reason", "actual_date"), "plant_waste", "plants_by_id", supports_bulk=True),
        _action("harvest_package", "Package harvest", "harvest", ("quantity", "unit", "tag", "item", "actual_date"), "harvest_packages", "packages_by_id", execution_path="specialized_verified", supports_bulk=True, catalog_visible=False),
        _action("harvest_move", "Move harvest", "harvest", ("destination_location",), "harvest_location_update", "harvests_by_id"),
        _action("harvest_waste", "Record harvest waste", "harvest", ("quantity", "unit", "reason", "actual_date"), "harvest_waste", "harvests_by_id", execution_path="specialized_verified", catalog_visible=False),
        _action("harvest_finish", "Finish harvest", "harvest", ("actual_date",), "harvest_finish", "harvests_by_id", execution_path="specialized_verified", catalog_visible=False),
        _action("harvest_unfinish", "Reopen harvest", "harvest", (), "harvest_unfinish", "harvests_by_id", execution_path="specialized_verified", catalog_visible=False),
        _action("transfer_create", "Create transfer", "transfer", ("destination_license", "package_ids"), "transfer_template_create", "transfer_templates_outgoing", roles=SUPERVISOR_ROLES, execution_path="shared_dispatch", supports_bulk=True),
        _action("manifest_update", "Update manifest", "transfer", ("manifest_reference",), "transfer_template_update", "transfer_templates_outgoing", roles=SUPERVISOR_ROLES),
        _action("production_transform", "Complete production run", "production_order", ("input_package_ids", "output_package_ids"), "package_create", "packages_by_id", roles=frozenset({"dev", "admin", "planner", "supervisor", "qa"}), execution_path="compound_specialized", supports_bulk=True),
        _action("lab_test_update", "Record lab result", "package", ("lab_status",), "lab_test_record", "lab_results", roles=SUPERVISOR_ROLES),
        _action("sales_report", "Report sales", "sales_period", ("period_start", "period_end"), "sales_receipt_upsert", "sales_receipts_active", roles=SUPERVISOR_ROLES, supports_bulk=True),
        _action("waste_record", "Record waste", "waste", ("quantity", "unit", "reason"), "plant_waste", "plants_by_id", supports_bulk=True),
    )
}


def get_traceability_action(name: str) -> TraceabilityActionDefinition | None:
    return TRACEABILITY_ACTIONS.get(str(name or "").strip().casefold())


def list_traceability_actions() -> tuple[TraceabilityActionDefinition, ...]:
    return tuple(TRACEABILITY_ACTIONS.values())
