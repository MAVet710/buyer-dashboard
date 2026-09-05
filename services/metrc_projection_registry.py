from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProjectionMode = Literal[
    "canonical_materialization",
    "provider_backed_read_model",
    "reference_data",
    "selector_mirror",
]
AuthorityClass = Literal[
    "regulated_authoritative",
    "provider_owned_history",
    "provider_reference",
]


@dataclass(frozen=True)
class MetrcProjectionSpec:
    resource: str
    mode: ProjectionMode
    authority: AuthorityClass
    destinations: tuple[str, ...]
    identity_strategy: str
    absence_semantics: str
    customer_visible: bool = True

    def public(self) -> dict[str, object]:
        return {
            "resource": self.resource,
            "mode": self.mode,
            "authority": self.authority,
            "destinations": list(self.destinations),
            "identity_strategy": self.identity_strategy,
            "absence_semantics": self.absence_semantics,
            "customer_visible": self.customer_visible,
        }


def _spec(
    resource: str,
    mode: ProjectionMode,
    authority: AuthorityClass,
    destinations: tuple[str, ...],
    *,
    identity: str = "exact_provider_id_with_facility_license_scope",
    absence: str = "never_infer_from_incremental_omission",
) -> MetrcProjectionSpec:
    return MetrcProjectionSpec(
        resource=resource,
        mode=mode,
        authority=authority,
        destinations=destinations,
        identity_strategy=identity,
        absence_semantics=absence,
    )


# This is the product contract for authenticated Metrc resources intentionally
# synchronized by the natural facility runtime. A resource may remain provider-owned
# history, but it may not silently terminate in the integration mirror with no named
# native DoobieLogic destination.
METRC_PROJECTION_REGISTRY: dict[str, MetrcProjectionSpec] = {
    # Facility / master / reference data.
    "locations": _spec(
        "locations", "canonical_materialization", "regulated_authoritative",
        ("facility_setup", "cultivation", "production"),
        absence="active_collection_no_terminal_inference",
    ),
    "locations_inactive": _spec(
        "locations_inactive", "reference_data", "provider_reference",
        ("facility_setup",),
    ),
    "sublocations": _spec(
        "sublocations", "reference_data", "provider_reference",
        ("facility_setup", "inventory", "production"),
    ),
    "sublocations_inactive": _spec(
        "sublocations_inactive", "reference_data", "provider_reference",
        ("facility_setup",),
    ),
    "location_types": _spec(
        "location_types", "reference_data", "provider_reference",
        ("facility_setup",),
    ),
    "strains": _spec(
        "strains", "reference_data", "provider_reference",
        ("cultivation", "product_master"),
    ),
    "strains_inactive": _spec(
        "strains_inactive", "reference_data", "provider_reference",
        ("cultivation", "product_master"),
    ),
    "items": _spec(
        "items", "canonical_materialization", "regulated_authoritative",
        ("product_master", "inventory", "production", "label_studio"),
    ),
    "items_inactive": _spec(
        "items_inactive", "reference_data", "provider_reference",
        ("product_master",),
    ),
    "item_categories": _spec(
        "item_categories", "reference_data", "provider_reference",
        ("product_master", "facility_setup"),
    ),
    "item_brands": _spec(
        "item_brands", "reference_data", "provider_reference",
        ("product_master", "facility_setup"),
    ),
    "units_of_measure": _spec(
        "units_of_measure", "reference_data", "provider_reference",
        ("product_master", "inventory", "production"),
        identity="provider_reference_code_or_name",
    ),

    # Tags and package inventory.
    "package_tags": _spec(
        "package_tags", "selector_mirror", "regulated_authoritative",
        ("inventory", "package_studio", "label_studio"),
        identity="exact_metrc_tag",
        absence="complete_available_tag_snapshot_controls_selector_membership",
    ),
    "plant_tags": _spec(
        "plant_tags", "selector_mirror", "regulated_authoritative",
        ("cultivation", "tag_inventory"),
        identity="exact_metrc_tag",
        absence="complete_available_tag_snapshot_controls_selector_membership",
    ),
    "packages": _spec(
        "packages", "canonical_materialization", "regulated_authoritative",
        ("inventory", "production", "package_studio", "label_studio"),
        identity="exact_metrc_package_id_and_label",
        absence="complete_active_snapshot_may_close_linked_package_incremental_omission_never_does",
    ),

    # Cultivation and post-harvest lifecycle.
    "plant_batches": _spec(
        "plant_batches", "canonical_materialization", "regulated_authoritative",
        ("cultivation", "nursery"),
        absence="active_collection_no_terminal_inference",
    ),
    "plants_vegetative": _spec(
        "plants_vegetative", "canonical_materialization", "regulated_authoritative",
        ("cultivation",),
        identity="exact_metrc_plant_id_and_tag",
        absence="active_collection_no_terminal_inference",
    ),
    "plants_flowering": _spec(
        "plants_flowering", "canonical_materialization", "regulated_authoritative",
        ("cultivation",),
        identity="exact_metrc_plant_id_and_tag",
        absence="active_collection_no_terminal_inference",
    ),
    "harvests": _spec(
        "harvests", "canonical_materialization", "regulated_authoritative",
        ("cultivation", "post_harvest"),
        absence="active_collection_no_terminal_inference",
    ),
    "additive_templates": _spec(
        "additive_templates", "reference_data", "provider_reference",
        ("cultivation", "production"),
    ),
    "additive_templates_inactive": _spec(
        "additive_templates_inactive", "reference_data", "provider_reference",
        ("cultivation", "production"),
    ),

    # Production / manufacturing.
    "processing_jobs": _spec(
        "processing_jobs", "provider_backed_read_model", "provider_owned_history",
        ("production", "manufacturing"),
        absence="provider_snapshot_membership_only_no_fabricated_local_job",
    ),
    "processing_job_types": _spec(
        "processing_job_types", "reference_data", "provider_reference",
        ("production", "manufacturing"),
    ),
    "processing_job_types_inactive": _spec(
        "processing_job_types_inactive", "reference_data", "provider_reference",
        ("production", "manufacturing"),
    ),
    "processing_job_attributes": _spec(
        "processing_job_attributes", "reference_data", "provider_reference",
        ("production", "manufacturing"),
    ),
    "processing_job_categories": _spec(
        "processing_job_categories", "reference_data", "provider_reference",
        ("production", "manufacturing"),
    ),

    # Transfers / receiving / wholesale / logistics. Provider history is visible in
    # native modules without inventing a local receiving or manifest action.
    "incoming_transfers": _spec(
        "incoming_transfers", "provider_backed_read_model", "provider_owned_history",
        ("receiving", "transfer_control"),
    ),
    "outgoing_transfers": _spec(
        "outgoing_transfers", "provider_backed_read_model", "provider_owned_history",
        ("wholesale", "fulfillment", "transfer_control"),
    ),
    "rejected_transfers": _spec(
        "rejected_transfers", "provider_backed_read_model", "provider_owned_history",
        ("receiving", "transfer_control"),
    ),
    "transfer_templates_outgoing": _spec(
        "transfer_templates_outgoing", "provider_backed_read_model", "provider_owned_history",
        ("wholesale", "logistics"),
    ),
    "transport_drivers": _spec(
        "transport_drivers", "reference_data", "provider_reference",
        ("logistics", "transportation"),
    ),
    "transport_vehicles": _spec(
        "transport_vehicles", "reference_data", "provider_reference",
        ("logistics", "transportation"),
    ),

    # Retail / delivery. Provider-owned records are projected, not fabricated as
    # DoobieLogic POS transactions.
    "sales_receipts": _spec(
        "sales_receipts", "provider_backed_read_model", "provider_owned_history",
        ("retail", "sales"),
    ),
    "sales_deliveries": _spec(
        "sales_deliveries", "provider_backed_read_model", "provider_owned_history",
        ("retail", "delivery"),
    ),
}


def projection_for_resource(resource: str) -> MetrcProjectionSpec | None:
    return METRC_PROJECTION_REGISTRY.get(str(resource or "").strip())


def projection_manifest() -> list[dict[str, object]]:
    return [METRC_PROJECTION_REGISTRY[name].public() for name in sorted(METRC_PROJECTION_REGISTRY)]


def missing_projection_resources(resources: set[str] | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(resource) for resource in resources if str(resource) not in METRC_PROJECTION_REGISTRY}))
