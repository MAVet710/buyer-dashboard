from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.schemas.inventory import InventoryReceiptCreate
from backend.app.services.receiving_preflight import ReceivingPreflightService
from modules.coman.models import Base, InventoryLot, utc_now
from modules.coman.repository import ComanRepository
from modules.traceability.models import ReceivingPreflight


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    organization = repo.create_organization("Receiving Preflight QA")
    facility = repo.create_facility(organization.id, "Retail", "RETAIL")
    product = repo.create_product(
        organization.id,
        sku="FLOWER-1",
        name="Verified Flower",
        item_type="cannabis",
        base_unit="g",
        actor="qa",
    )
    metrc = SimpleNamespace(
        configured=True,
        status="connected",
        trusted_mapping=True,
        state="MA",
        environment="sandbox",
        license_number="MR-RECEIVE-1",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
    )
    return engine, organization, facility, product, metrc


def _snapshot(quantity: str = "10", *, lab_state: str = "TestPassed") -> dict:
    return {
        "ok": True,
        "status": "verified_read",
        "transfer_id": "77",
        "manifest": "MAN-77",
        "vendor": "Source Facility",
        "vendor_license": "MP-SOURCE",
        "packages": [
            {
                "package_record_id": "7001",
                "package_id": "1A4PKG000000000000000001",
                "identity": "1A4PKG000000000000000001",
                "quantity": quantity,
                "unit": "g",
                "unit_key": "g",
                "lab_testing_state": lab_state,
                "delivery_id": "9001",
            }
        ],
    }


def _receipt(product_id: str, *, quantity: float = 10, unit: str = "g") -> InventoryReceiptCreate:
    return InventoryReceiptCreate(
        product_id=product_id,
        package_id="1A4PKG000000000000000001",
        lot_code="1A4PKG000000000000000001",
        quantity=quantity,
        unit=unit,
        location="RECEIVING",
        source_name="client supplied source must not win",
        manifest_reference="client supplied manifest must not win",
        lab_testing_state="client supplied lab state must not win",
        coa_reference="operator-coa-note",
        notes="physical count reviewed",
    )


def test_matching_provider_readback_posts_atomic_receipt_and_overwrites_provider_controlled_metadata(monkeypatch):
    engine, organization, facility, product, metrc = _setup()
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: _snapshot())
    service = ReceivingPreflightService(engine)

    prepared = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )
    assert prepared["status"] == "prepared"
    result = service.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        preflight_id=prepared["id"],
        transfer_id="77",
        rows=[_receipt(product.id)],
        metrc=metrc,
    )

    assert result["preflight"]["status"] == "consumed"
    assert result["idempotent"] is False
    assert len(result["receipts"]) == 1
    with Session(engine) as session:
        lot = session.scalar(select(InventoryLot).where(InventoryLot.compliance_package_id == "1A4PKG000000000000000001"))
        assert lot is not None
        metadata = json.loads(lot.notes)
        assert metadata["source_name"] == "Source Facility"
        assert metadata["manifest_reference"] == "MAN-77"
        assert metadata["lab_testing_state"] == "TestPassed"
        assert metadata["coa_reference"] == "operator-coa-note"


def test_provider_change_marks_preflight_stale_and_posts_nothing(monkeypatch):
    engine, organization, facility, product, metrc = _setup()
    snapshots = iter([_snapshot("10"), _snapshot("9")])
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: next(snapshots))
    service = ReceivingPreflightService(engine)
    prepared = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )

    with pytest.raises(ValueError, match="Metrc changed after review"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="77",
            rows=[_receipt(product.id)],
            metrc=metrc,
        )
    with Session(engine) as session:
        row = session.get(ReceivingPreflight, prepared["id"])
        assert row is not None and row.status == "stale"
        assert session.scalar(select(InventoryLot.id).where(InventoryLot.facility_id == facility.id)) is None


def test_expired_preflight_persists_stale_status_before_error(monkeypatch):
    engine, organization, facility, product, metrc = _setup()
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: _snapshot())
    service = ReceivingPreflightService(engine)
    prepared = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )
    with Session(engine) as session, session.begin():
        row = session.get(ReceivingPreflight, prepared["id"])
        assert row is not None
        row.expires_at = utc_now() - timedelta(minutes=1)

    with pytest.raises(ValueError, match="provider confirmation expired"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="77",
            rows=[_receipt(product.id)],
            metrc=metrc,
        )
    with Session(engine) as session:
        row = session.get(ReceivingPreflight, prepared["id"])
        assert row is not None and row.status == "stale"


def test_processing_preflight_blocks_blind_retry_before_provider_call(monkeypatch):
    engine, organization, facility, product, metrc = _setup()
    calls = 0

    def provider(**_):
        nonlocal calls
        calls += 1
        return _snapshot()

    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", provider)
    service = ReceivingPreflightService(engine)
    prepared = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )
    with Session(engine) as session, session.begin():
        row = session.get(ReceivingPreflight, prepared["id"])
        assert row is not None
        row.status = "processing"

    with pytest.raises(ValueError, match="unknown local outcome"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="77",
            rows=[_receipt(product.id)],
            metrc=metrc,
        )
    assert calls == 1


def test_unexpected_local_error_intentionally_leaves_processing_for_reconciliation(monkeypatch):
    engine, organization, facility, product, metrc = _setup()
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: _snapshot())
    monkeypatch.setattr(
        "backend.app.services.receiving_preflight.InventoryReceiptBatchService.post",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("simulated process interruption")),
    )
    service = ReceivingPreflightService(engine)
    prepared = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )

    with pytest.raises(RuntimeError, match="simulated process interruption"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="77",
            rows=[_receipt(product.id)],
            metrc=metrc,
        )
    with Session(engine) as session:
        row = session.get(ReceivingPreflight, prepared["id"])
        assert row is not None and row.status == "processing"


def test_reviewed_package_set_quantity_unit_and_transfer_are_exactly_bound(monkeypatch):
    engine, organization, facility, product, metrc = _setup()
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: _snapshot())
    service = ReceivingPreflightService(engine)
    prepared = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )
    with pytest.raises(ValueError, match="does not belong to this inbound transfer"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="88",
            rows=[_receipt(product.id)],
            metrc=metrc,
        )
    with pytest.raises(ValueError, match="quantity no longer matches"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="77",
            rows=[_receipt(product.id, quantity=11)],
            metrc=metrc,
        )


def test_receiving_preflight_contract_is_registered_read_only_and_migrated():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    router = (root / "backend/app/routers/receiving_preflight.py").read_text(encoding="utf-8")
    regulatory_router = (root / "backend/app/routers/inventory_reconciliation.py").read_text(encoding="utf-8")
    helper = (root / "services/metrc_receiving.py").read_text(encoding="utf-8")
    frontend = (root / "frontend/src/components/ReceiveInventory.tsx").read_text(encoding="utf-8")
    migration = (root / "migrations/versions/0055_receiving_preflight.py").read_text(encoding="utf-8")

    assert '@router.post("/{operation}/inbound/{transfer_id}/preflight"' in router
    assert '@router.post("/{operation}/inbound/{transfer_id}/preflight/commit")' in router
    assert "router.include_router(receiving_preflight_router)" in regulatory_router
    assert "fetch_confirmed_inbound_snapshot" in helper
    assert "_metrc_post" not in helper
    assert "Confirm provider state & review" in frontend
    assert "Verify again & Post Inventory" in frontend
    assert "Provider controlled" in frontend
    assert 'revision = "0055_receiving_preflight"' in migration
    assert 'down_revision = "0054_storefront_sales_units"' in migration
