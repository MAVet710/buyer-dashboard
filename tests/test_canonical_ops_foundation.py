from __future__ import annotations

import json

import pytest

from modules.canonical_cannabis import (
    CannabisEntityType,
    canonical_entity_type,
    operational_correlation_id,
    provider_resource_entity,
)
from modules.coman.audit import build_audit_payload, parse_audit_payload, record_audit_event
from modules.traceability.provider_contract import (
    ProviderExecutionResult,
    TraceabilityCapability,
    TraceabilityProviderRegistry,
    normalize_provider_result,
)


def test_canonical_cannabis_vocabulary_normalizes_provider_terms_without_replacing_domain_models():
    assert provider_resource_entity("metrc", "Packages") == CannabisEntityType.INVENTORY_LOT
    assert provider_resource_entity("metrc", "PlantBatches") == CannabisEntityType.PLANT_BATCH
    assert canonical_entity_type("purchaseOrder") == CannabisEntityType.PURCHASE_ORDER
    assert canonical_entity_type("Future Provider Resource") == "future_provider_resource"
    assert operational_correlation_id("receiving batch", "MAN-1001") == "receiving_batch:MAN-1001"


def test_audit_envelope_preserves_legacy_top_level_changes():
    payload = build_audit_payload(
        {"quantity": 24, "unit": "unit", "manifest_reference": "MAN-1"},
        source="rfid",
        reason="Inbound package observed and reviewed.",
        correlation_id="receiving:abc",
        before={"status": "inbound"},
        after={"status": "available"},
        device={"adapter": "test-reader"},
    )
    assert payload["quantity"] == 24
    assert payload["manifest_reference"] == "MAN-1"
    assert payload["_event"]["schema_version"] == 1
    assert payload["_event"]["source"] == "rfid"
    assert payload["_event"]["correlation_id"] == "receiving:abc"
    assert payload["_event"]["after"]["status"] == "available"


def test_legacy_audit_payloads_remain_readable():
    payload = parse_audit_payload('{"quantity": 1, "unit": "g"}')
    assert payload["quantity"] == 1
    assert payload["_event"]["schema_version"] == 0
    assert payload["_event"]["legacy"] is True


def test_record_audit_event_uses_existing_audit_event_model_and_canonical_entity_name():
    class FakeSession:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

    session = FakeSession()
    row = record_audit_event(
        session,
        organization_id="org-1",
        facility_id="fac-1",
        entity_type="package",
        entity_id="lot-1",
        action="received",
        actor="operator-1",
        changes={"quantity": 12},
        source="scanner",
        correlation_id="receiving:1",
    )
    assert session.rows == [row]
    assert row.entity_type == "inventory_lot"
    decoded = json.loads(row.changes_json)
    assert decoded["quantity"] == 12
    assert decoded["_event"]["source"] == "scanner"


def test_audit_source_is_fail_closed():
    with pytest.raises(ValueError, match="Unsupported audit source"):
        build_audit_payload({}, source="unreviewed_magic")


def test_provider_result_normalizes_existing_adapter_dicts():
    result = normalize_provider_result(
        "metrc",
        {
            "ok": True,
            "status": "accepted",
            "outbound_request_sent": True,
            "verified": False,
            "http_status": 200,
            "external_reference": "EXT-1",
        },
        verification_resource="packages",
    )
    assert isinstance(result, ProviderExecutionResult)
    assert result.provider == "metrc"
    assert result.request_sent is True
    assert result.verified is False
    assert result.verification_resource == "packages"
    assert result.as_dict()["outbound_request_sent"] is True


def test_provider_registry_declares_capability_without_granting_write_access():
    class FakeAdapter:
        provider = "metrc"

        def capabilities(self):
            return {
                "package_adjustment": TraceabilityCapability(
                    operation_type="package_adjustment",
                    verification_resource="packages",
                    supports_write=True,
                    supports_readback=True,
                )
            }

        def execute(self, *, operation_type, entity_id, payload, reason):
            return ProviderExecutionResult(
                provider="metrc",
                ok=True,
                status="accepted",
                request_sent=True,
                verified=False,
            )

    registry = TraceabilityProviderRegistry()
    registry.register(FakeAdapter())
    capability = registry.capabilities("METRC")["package_adjustment"]
    assert capability.supports_write is True
    assert capability.supports_readback is True
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeAdapter())
