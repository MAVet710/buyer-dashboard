from __future__ import annotations

from services.metrc_natural_bootstrap import NaturalMetrcFacilityBootstrapService
from services.metrc_projection_registry import (
    METRC_PROJECTION_REGISTRY,
    missing_projection_resources,
    projection_for_resource,
)


def _runtime_resources() -> set[str]:
    normalized = {name for name, _resource in NaturalMetrcFacilityBootstrapService.NORMALIZED_RESOURCES}
    direct = {name for name, _path, _paginated in NaturalMetrcFacilityBootstrapService.DIRECT_RESOURCES}
    return normalized | direct


def test_every_authenticated_runtime_resource_has_a_declared_native_projection():
    runtime_resources = _runtime_resources()
    assert runtime_resources
    assert missing_projection_resources(runtime_resources) == ()


def test_projection_registry_has_no_empty_customer_destination():
    for resource in _runtime_resources():
        spec = projection_for_resource(resource)
        assert spec is not None, resource
        assert spec.customer_visible is True
        assert spec.destinations, resource
        assert all(destination.strip() for destination in spec.destinations)
        assert spec.identity_strategy
        assert spec.absence_semantics


def test_provider_history_is_projected_without_fabricating_local_transactions():
    for resource in (
        "incoming_transfers",
        "outgoing_transfers",
        "rejected_transfers",
        "processing_jobs",
        "sales_receipts",
        "sales_deliveries",
    ):
        spec = METRC_PROJECTION_REGISTRY[resource]
        assert spec.mode == "provider_backed_read_model"
        assert spec.authority == "provider_owned_history"


def test_regulated_operational_objects_use_canonical_or_selector_projection():
    for resource in (
        "items",
        "packages",
        "plant_batches",
        "plants_vegetative",
        "plants_flowering",
        "harvests",
    ):
        spec = METRC_PROJECTION_REGISTRY[resource]
        assert spec.mode == "canonical_materialization"
        assert spec.authority == "regulated_authoritative"

    assert METRC_PROJECTION_REGISTRY["package_tags"].mode == "selector_mirror"
    assert METRC_PROJECTION_REGISTRY["plant_tags"].mode == "selector_mirror"


def test_projection_registry_declares_native_operator_destinations():
    assert "inventory" in METRC_PROJECTION_REGISTRY["packages"].destinations
    assert "cultivation" in METRC_PROJECTION_REGISTRY["plants_vegetative"].destinations
    assert "post_harvest" in METRC_PROJECTION_REGISTRY["harvests"].destinations
    assert "receiving" in METRC_PROJECTION_REGISTRY["incoming_transfers"].destinations
    assert "wholesale" in METRC_PROJECTION_REGISTRY["outgoing_transfers"].destinations
    assert "production" in METRC_PROJECTION_REGISTRY["processing_jobs"].destinations
    assert "retail" in METRC_PROJECTION_REGISTRY["sales_receipts"].destinations
