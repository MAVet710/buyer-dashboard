from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.inventory_reconciliation import InventoryMetrcReconciliationService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="DoobieLogic Test", slug="doobielogic-test"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Production", code="PROD"))
        session.add(Product(
            id="product-1",
            organization_id="org-1",
            sku="FLOWER-1",
            name="Bulk Flower",
            item_type="cannabis",
            base_unit="g",
        ))
        session.flush()
        session.add(InventoryLot(
            id="lot-1",
            organization_id="org-1",
            facility_id="fac-1",
            product_id="product-1",
            lot_code="LOT-1",
            compliance_package_id="1A4000000000000000000001",
            location_code="Bulk Vault",
            status="available",
            notes=json.dumps({"lab_testing_state": "TestPassed"}),
        ))
        session.flush()
        session.add(InventoryTransaction(
            organization_id="org-1",
            facility_id="fac-1",
            lot_id="lot-1",
            transaction_type="receive",
            quantity_delta=100,
            unit="g",
            reason="Receipt",
            reference="MAN-1",
            actor="tester",
        ))
        session.commit()
    return engine


def _record(label: str, quantity: float, unit: str = "Grams", *, location: str = "Bulk Vault", lab: str = "TestPassed"):
    return {
        "provider": "metrc",
        "jurisdiction_code": "MA",
        "resource": "packages_active",
        "provider_id": "99",
        "label": label,
        "name": "Bulk Flower",
        "status": lab,
        "quantity": quantity,
        "unit_of_measure": unit,
        "source": {
            "Id": 99,
            "Label": label,
            "Quantity": quantity,
            "UnitOfMeasureName": unit,
            "LocationName": location,
            "LabTestingState": lab,
        },
    }


def test_reconciliation_matches_physical_ledger_with_safe_unit_conversion():
    report = InventoryMetrcReconciliationService(_engine()).reconcile(
        "org-1",
        "fac-1",
        jurisdiction_code="MA",
        license_number="MP281281",
        environment="production",
        metrc_records=[_record("1A4000000000000000000001", 0.1, "Kilograms")],
        evidence={"source_url": "https://api-ma.metrc.com/Documentation/"},
    )

    assert report["read_only"] is True
    assert report["summary"]["status"] == "clean"
    assert report["summary"]["matched_package_count"] == 1
    assert report["summary"]["discrepancy_count"] == 0
    assert report["evidence"]["source_url"] == "https://api-ma.metrc.com/Documentation/"


def test_reconciliation_surfaces_quantity_location_lab_and_missing_package_differences():
    engine = _engine()
    report = InventoryMetrcReconciliationService(engine).reconcile(
        "org-1",
        "fac-1",
        jurisdiction_code="MA",
        license_number="MP281281",
        environment="production",
        metrc_records=[
            _record("1A4000000000000000000001", 92, location="Quarantine", lab="TestFailed"),
            _record("1A4000000000000000000002", 50),
        ],
    )

    codes = [row["code"] for row in report["discrepancies"]]
    assert "quantity_mismatch" in codes
    assert "location_mismatch" in codes
    assert "lab_state_mismatch" in codes
    assert "missing_in_doobielogic" in codes
    assert report["summary"]["high_count"] == 2
    assert report["summary"]["medium_count"] == 2
    assert report["summary"]["status"] == "attention"


def test_reconciliation_flags_local_positive_balance_missing_from_active_metrc():
    report = InventoryMetrcReconciliationService(_engine()).reconcile(
        "org-1",
        "fac-1",
        jurisdiction_code="MA",
        license_number="MP281281",
        environment="production",
        metrc_records=[],
    )

    assert report["summary"]["discrepancy_count"] == 1
    assert report["discrepancies"][0]["code"] == "missing_in_metrc"
    assert report["discrepancies"][0]["local_quantity"] == 100


def test_reconciliation_detects_duplicate_local_traceability_package_ids():
    engine = _engine()
    with Session(engine) as session:
        session.add(InventoryLot(
            id="lot-2",
            organization_id="org-1",
            facility_id="fac-1",
            product_id="product-1",
            lot_code="LOT-2",
            compliance_package_id="1A4000000000000000000001",
            location_code="Bulk Vault",
            status="available",
        ))
        session.flush()
        session.add(InventoryTransaction(
            organization_id="org-1",
            facility_id="fac-1",
            lot_id="lot-2",
            transaction_type="receive",
            quantity_delta=25,
            unit="g",
            reason="Receipt",
            reference="MAN-2",
            actor="tester",
        ))
        session.commit()

    report = InventoryMetrcReconciliationService(engine).reconcile(
        "org-1",
        "fac-1",
        jurisdiction_code="MA",
        license_number="MP281281",
        environment="production",
        metrc_records=[_record("1A4000000000000000000001", 125)],
    )

    assert report["summary"]["discrepancy_count"] == 1
    assert report["discrepancies"][0]["code"] == "duplicate_local_package"
    assert report["discrepancies"][0]["severity"] == "high"
