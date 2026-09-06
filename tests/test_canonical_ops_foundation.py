from __future__ import annotations

from datetime import date
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.schemas.inventory import InventoryReceiptCreate
from backend.app.services.inventory_receiving import InventoryReceiptBatchService
from modules.canonical_cannabis import (
    CannabisEntityType,
    canonical_entity_type,
    operational_correlation_id,
    provider_resource_entity,
)
from modules.coman.audit import build_audit_payload, parse_audit_payload, record_audit_event
from modules.coman.models import AuditEvent, Base, InventoryTransaction
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
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


def test_receipt_contract_can_link_real_purchase_order_and_line_fields_without_breaking_unlinked_receipts():
    unlinked = InventoryReceiptCreate(product_id="product-1", quantity=12, unit="unit")
    assert unlinked.commercial_order_id == ""
    assert unlinked.commercial_order_line_id == ""

    linked = InventoryReceiptCreate(
        product_id="product-1",
        quantity=12,
        unit="unit",
        commercial_order_id="po-1",
        commercial_order_line_id="po-line-1",
    )
    assert linked.commercial_order_id == "po-1"
    assert linked.commercial_order_line_id == "po-line-1"


def test_purchase_order_receiving_links_inventory_and_fulfillment_atomically():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)
    org = coman.create_organization("Canonical Receiving QA")
    facility = coman.create_facility(org.id, "Main", "MAIN")
    product = coman.create_product(
        org.id,
        sku="GMO-PR-1G",
        name="GMO Pre-Roll 1g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=4,
        actor="dev",
    )
    vendor = commercial.create_trade_partner(
        org.id,
        name="Licensed Vendor",
        partner_type="vendor",
        actor="dev",
    )
    order = commercial.create_order(
        organization_id=org.id,
        facility_id=facility.id,
        partner_id=vendor.id,
        order_number="PO-CANONICAL-1",
        order_type="purchase",
        order_date=date.today(),
        due_date=date.today(),
        lines=[
            {
                "product_id": product.id,
                "quantity": 10,
                "unit_price": 4,
                "unit": "unit",
            }
        ],
        actor="dev",
    )
    commercial.confirm_order(
        order.id,
        organization_id=org.id,
        facility_id=facility.id,
        actor="dev",
    )
    line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    receiving = InventoryReceiptBatchService(engine)

    first = receiving.post(
        org.id,
        facility.id,
        operation="production",
        actor="receiver",
        rows=[
            InventoryReceiptCreate(
                product_id=product.id,
                lot_code="GMO-IN-001",
                package_id="1A-PACKAGE-001",
                quantity=4,
                unit="unit",
                commercial_order_id=order.id,
                commercial_order_line_id=line.id,
                manifest_reference="MAN-001",
            )
        ],
    )
    partial_order = commercial.list_orders(org.id, facility.id)[0]
    partial_line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    assert partial_order.status == "partially_fulfilled"
    assert partial_line.fulfilled_quantity == pytest.approx(4)

    with Session(engine) as session:
        first_txn = session.get(InventoryTransaction, first[0].transaction_id)
        assert first_txn is not None
        assert first_txn.commercial_order_id == order.id
        assert first_txn.commercial_order_line_id == line.id
        lot_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "inventory_lot",
                AuditEvent.entity_id == first[0].lot_id,
                AuditEvent.action == "production_inventory_received",
            )
        )
        assert lot_event is not None
        envelope = json.loads(lot_event.changes_json)["_event"]
        assert envelope["correlation_id"] == f"purchase_order:{order.id}"
        assert envelope["metadata"]["inventory_transaction_id"] == first[0].transaction_id

    second = receiving.post(
        org.id,
        facility.id,
        operation="production",
        actor="receiver",
        rows=[
            InventoryReceiptCreate(
                product_id=product.id,
                lot_code="GMO-IN-002",
                package_id="1A-PACKAGE-002",
                quantity=6,
                unit="unit",
                commercial_order_id=order.id,
                commercial_order_line_id=line.id,
                manifest_reference="MAN-002",
            )
        ],
    )
    assert second[0].status == "available"
    fulfilled_order = commercial.list_orders(org.id, facility.id)[0]
    fulfilled_line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    assert fulfilled_order.status == "fulfilled"
    assert fulfilled_line.fulfilled_quantity == pytest.approx(10)

    with pytest.raises(ValueError, match="exceed"):
        receiving.post(
            org.id,
            facility.id,
            operation="production",
            actor="receiver",
            rows=[
                InventoryReceiptCreate(
                    product_id=product.id,
                    lot_code="GMO-IN-003",
                    package_id="1A-PACKAGE-003",
                    quantity=1,
                    unit="unit",
                    commercial_order_id=order.id,
                    commercial_order_line_id=line.id,
                )
            ],
        )


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
