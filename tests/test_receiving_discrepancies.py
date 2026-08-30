from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.receiving_preflight import _require_preflight_transfer
from backend.app.schemas.inventory import InventoryReceiptCreate
from backend.app.services.receiving_preflight import ReceivingPreflightService
from modules.coman.models import Base, InventoryLot
from modules.coman.repository import ComanRepository
from modules.traceability.models import ReceivingDiscrepancy


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    organization = repo.create_organization("Receiving Exception QA")
    facility = repo.create_facility(organization.id, "Retail", "RETAIL")
    product = repo.create_product(
        organization.id,
        sku="FLOWER-EX",
        name="Exception Flower",
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
        license_number="MR-EXCEPT-1",
        user_api_key="user-key",
        integrator_api_key="integrator-key",
    )
    context = RequestContext(
        user_id="supervisor-1",
        organization_id=organization.id,
        facility_id=facility.id,
        role="supervisor",
    )
    return engine, repo, organization, facility, product, metrc, context


def _snapshot(quantity: str = "10") -> dict:
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
                "lab_testing_state": "TestPassed",
                "delivery_id": "9001",
            }
        ],
    }


def _receipt(product_id: str) -> InventoryReceiptCreate:
    return InventoryReceiptCreate(
        product_id=product_id,
        package_id="1A4PKG000000000000000001",
        lot_code="1A4PKG000000000000000001",
        quantity=10,
        unit="g",
        location="RECEIVING",
        source_name="source",
        manifest_reference="manifest",
        lab_testing_state="TestPassed",
        coa_reference="",
        notes="",
    )


def _observation(quantity: float = 10, *, condition: str = "ok", package_id: str = "1A4PKG000000000000000001", note: str = "") -> dict:
    return {
        "package_id": package_id,
        "observed_quantity": quantity,
        "unit": "g",
        "condition": condition,
        "note": note,
    }


def _prepare(monkeypatch, engine, organization, facility, metrc):
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: _snapshot())
    return ReceivingPreflightService(engine).prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )


def test_exact_physical_observation_creates_no_discrepancy(monkeypatch):
    engine, _repo, organization, facility, _product, metrc, _context = _setup()
    prepared = _prepare(monkeypatch, engine, organization, facility, metrc)
    result = ReceivingPreflightService(engine).record_observations(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        preflight_id=prepared["id"],
        transfer_id="77",
        observations=[_observation()],
    )
    assert result["can_post"] is True
    assert result["discrepancies"] == []
    with Session(engine) as session:
        assert session.scalar(select(ReceivingDiscrepancy.id)) is None


@pytest.mark.parametrize(
    ("observations", "expected_type"),
    [
        ([_observation(9)], "short"),
        ([_observation(0)], "missing"),
        ([_observation(10, condition="damaged", note="seal broken")], "damaged"),
        ([_observation(), _observation(2, package_id="UNEXPECTED-PKG")], "unexpected"),
    ],
)
def test_physical_exceptions_are_durable_and_blocking(monkeypatch, observations, expected_type):
    engine, _repo, organization, facility, _product, metrc, _context = _setup()
    prepared = _prepare(monkeypatch, engine, organization, facility, metrc)
    result = ReceivingPreflightService(engine).record_observations(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        preflight_id=prepared["id"],
        transfer_id="77",
        observations=observations,
    )
    assert result["can_post"] is False
    assert any(row["discrepancy_type"] == expected_type and row["status"] == "open" for row in result["discrepancies"])
    with Session(engine) as session:
        rows = session.scalars(select(ReceivingDiscrepancy).where(ReceivingDiscrepancy.preflight_id == prepared["id"])).all()
        assert any(row.discrepancy_type == expected_type and row.status == "open" for row in rows)
        assert session.scalar(select(InventoryLot.id).where(InventoryLot.facility_id == facility.id)) is None


def test_open_discrepancy_blocks_receipt_before_second_provider_read(monkeypatch):
    engine, _repo, organization, facility, product, metrc, _context = _setup()
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
    service.record_observations(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        preflight_id=prepared["id"],
        transfer_id="77",
        observations=[_observation(9)],
    )
    with pytest.raises(ValueError, match="open physical discrepancy"):
        service.commit(
            organization_id=organization.id,
            facility_id=facility.id,
            operation="retail",
            actor="operator-1",
            preflight_id=prepared["id"],
            transfer_id="77",
            rows=[_receipt(product.id)],
            observations=[_observation()],
            metrc=metrc,
        )
    assert calls == 1
    with Session(engine) as session:
        assert session.scalar(select(InventoryLot.id).where(InventoryLot.facility_id == facility.id)) is None


def test_authorized_resolution_records_actor_and_does_not_mutate_inventory(monkeypatch):
    engine, _repo, organization, facility, _product, metrc, _context = _setup()
    prepared = _prepare(monkeypatch, engine, organization, facility, metrc)
    service = ReceivingPreflightService(engine)
    recorded = service.record_observations(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        preflight_id=prepared["id"],
        transfer_id="77",
        observations=[_observation(9, note="one gram short")],
    )
    discrepancy = recorded["discrepancies"][0]
    resolved = service.resolve_discrepancy(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="supervisor-1",
        preflight_id=prepared["id"],
        discrepancy_id=discrepancy["id"],
        resolution_note="Physical package reweighed and vendor contacted.",
    )
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == "supervisor-1"
    assert resolved["resolved_at"]
    assert "reweighed" in resolved["resolution_note"]
    with Session(engine) as session:
        assert session.scalar(select(InventoryLot.id).where(InventoryLot.facility_id == facility.id)) is None


def test_superseding_preflight_cancels_old_open_discrepancies(monkeypatch):
    engine, _repo, organization, facility, _product, metrc, _context = _setup()
    monkeypatch.setattr("backend.app.services.receiving_preflight.fetch_confirmed_inbound_snapshot", lambda **_: _snapshot())
    service = ReceivingPreflightService(engine)
    first = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        transfer_id="77",
        metrc=metrc,
    )
    recorded = service.record_observations(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-1",
        preflight_id=first["id"],
        transfer_id="77",
        observations=[_observation(9)],
    )
    second = service.prepare(
        organization_id=organization.id,
        facility_id=facility.id,
        operation="retail",
        actor="operator-2",
        transfer_id="77",
        metrc=metrc,
    )
    assert second["id"] != first["id"]
    with Session(engine) as session:
        old = session.get(ReceivingDiscrepancy, recorded["discrepancies"][0]["id"])
        assert old is not None
        assert old.status == "cancelled"
        assert old.resolved_by == "operator-2"
        assert "superseded" in old.resolution_note.casefold()


def test_discrepancy_scope_fails_closed_for_wrong_transfer_or_tenant(monkeypatch):
    engine, repo, organization, facility, _product, metrc, context = _setup()
    prepared = _prepare(monkeypatch, engine, organization, facility, metrc)
    with pytest.raises(HTTPException) as wrong_transfer:
        _require_preflight_transfer(
            engine=engine,
            context=context,
            operation="retail",
            transfer_id="WRONG",
            preflight_id=prepared["id"],
        )
    assert wrong_transfer.value.status_code == 404

    other_org = repo.create_organization("Hidden Receiving Org")
    other_facility = repo.create_facility(other_org.id, "Hidden", "HIDDEN")
    other_context = RequestContext(user_id="hidden", organization_id=other_org.id, facility_id=other_facility.id, role="admin")
    with pytest.raises(HTTPException) as wrong_tenant:
        _require_preflight_transfer(
            engine=engine,
            context=other_context,
            operation="retail",
            transfer_id="77",
            preflight_id=prepared["id"],
        )
    assert wrong_tenant.value.status_code == 404


def test_phase2_receiving_exception_contract_is_migrated_and_operator_visible():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    migration = (root / "migrations/versions/0057_receiving_discrepancies.py").read_text(encoding="utf-8")
    sql = (root / "migrations/versions/0057_receiving_discrepancies.sql").read_text(encoding="utf-8")
    router = (root / "backend/app/routers/receiving_preflight.py").read_text(encoding="utf-8")
    frontend = (root / "frontend/src/components/ReceiveInventory.tsx").read_text(encoding="utf-8")

    assert 'revision = "0057_receiving_discrepancies"' in migration
    assert 'down_revision = "0056_trace_reconciliation"' in migration
    assert "traceability_receiving_discrepancies" in sql
    assert "/preflight/discrepancies" in router
    assert "Physical count" in frontend
    assert "Record discrepancy & block receipt" in frontend
    assert "observations: physicalObservations" in frontend
    assert "METRC quantity" in frontend and "Provider controlled · never edited here" in frontend
