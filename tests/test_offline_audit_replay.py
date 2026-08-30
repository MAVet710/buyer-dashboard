from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.services.offline_audit_counts import IdempotentAuditCountService, OfflineMutationConflict
from modules.coman.models import (
    Base,
    Facility,
    InventoryAuditScan,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
)
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.offline.models import OfflineMutationReceipt


ROOT = Path(__file__).resolve().parents[1]


def _seed_audit():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Offline Test Org", slug="offline-test-org")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Offline Test Facility",
            code="OFFLINE-1",
            retail_enabled=True,
            production_enabled=True,
        )
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=organization.id,
            sku="OFFLINE-SKU",
            name="Offline Test Product",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=1.0,
            retail_price=2.0,
        )
        session.add(product)
        session.flush()
        lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="OFFLINE-LOT-1",
            barcode_value="OFFLINE-CODE-1",
            location_code="VAULT-A",
            status="available",
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=10.0,
                unit="unit",
                reason="test seed",
                reference="seed",
                actor="tester",
            )
        )
        organization_id = organization.id
        facility_id = facility.id
        lot_id = lot.id

    audit = InventoryAuditRepository(engine).create_audit(
        organization_id,
        facility_id,
        audit_number="OFFLINE-AUDIT-1",
        actor="tester",
        lot_ids=[lot_id],
        operation_type="retail",
        blind_count=True,
        recount_tolerance=0.0,
    )
    return engine, organization_id, facility_id, audit.id


def test_same_replay_key_and_payload_applies_physical_count_exactly_once():
    engine, organization_id, facility_id, audit_id = _seed_audit()
    service = IdempotentAuditCountService(engine)

    first = service.record(
        organization_id,
        facility_id,
        audit_id,
        raw_code="OFFLINE-CODE-1",
        quantity=7,
        actor="counter-1",
        idempotency_key="offline-count-1",
        reason="Count correction",
        notes="captured on floor",
    )
    replay = service.record(
        organization_id,
        facility_id,
        audit_id,
        raw_code="OFFLINE-CODE-1",
        quantity=7,
        actor="counter-1",
        idempotency_key="offline-count-1",
        reason="Count correction",
        notes="captured on floor",
    )

    assert first.id == replay.id
    assert replay.first_count_quantity == 7
    assert replay.counted_quantity == 7
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OfflineMutationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryAuditScan)) == 1


def test_reusing_replay_key_for_different_payload_is_a_human_review_conflict():
    engine, organization_id, facility_id, audit_id = _seed_audit()
    service = IdempotentAuditCountService(engine)
    service.record(
        organization_id,
        facility_id,
        audit_id,
        raw_code="OFFLINE-CODE-1",
        quantity=7,
        actor="counter-1",
        idempotency_key="offline-count-1",
    )

    with pytest.raises(OfflineMutationConflict, match="different physical count"):
        service.record(
            organization_id,
            facility_id,
            audit_id,
            raw_code="OFFLINE-CODE-1",
            quantity=8,
            actor="counter-1",
            idempotency_key="offline-count-1",
        )

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OfflineMutationReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryAuditScan)) == 1


def test_new_replay_key_cannot_overwrite_a_count_that_committed_while_device_was_offline():
    engine, organization_id, facility_id, audit_id = _seed_audit()
    service = IdempotentAuditCountService(engine)
    service.record(
        organization_id,
        facility_id,
        audit_id,
        raw_code="OFFLINE-CODE-1",
        quantity=7,
        actor="counter-1",
        idempotency_key="offline-count-1",
    )

    with pytest.raises(OfflineMutationConflict, match="received a first-pass count"):
        service.record(
            organization_id,
            facility_id,
            audit_id,
            raw_code="OFFLINE-CODE-1",
            quantity=7,
            actor="counter-2",
            idempotency_key="offline-count-2",
        )


def test_offline_replay_requires_explicit_scope_key_and_never_calls_provider_dispatch():
    engine, organization_id, facility_id, audit_id = _seed_audit()
    service = IdempotentAuditCountService(engine)
    with pytest.raises(ValueError, match="idempotency key is required"):
        service.record(
            organization_id,
            facility_id,
            audit_id,
            raw_code="OFFLINE-CODE-1",
            quantity=7,
            actor="counter-1",
            idempotency_key="",
        )

    service_source = (ROOT / "backend/app/services/offline_audit_counts.py").read_text(encoding="utf-8")
    router_source = (ROOT / "backend/app/routers/offline_inventory.py").read_text(encoding="utf-8")
    assert "ProviderRouter" not in service_source
    assert "TraceabilityDispatcher" not in service_source
    assert "requests." not in service_source
    assert 'alias="X-Idempotency-Key"' in router_source
    assert 'status_code=409' in router_source
    assert "/scan/count/replay" in router_source
