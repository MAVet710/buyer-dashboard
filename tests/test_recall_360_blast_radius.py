from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.inventory_transfers.recall import RecallBlastRadiusService
from modules.inventory_transfers.service import InventoryTransferService
from modules.material_lineage.service import MaterialLineageService

ROOT = Path(__file__).resolve().parents[1]


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Organization(id="org-recall", name="Recall Org", slug="recall-org"),
                Organization(id="org-other", name="Other Org", slug="other-recall-org"),
            ]
        )
        session.add_all(
            [
                Facility(
                    id="facility-source",
                    organization_id="org-recall",
                    name="Manufacturing License",
                    code="MFG",
                    license_number="MFG-001",
                    production_enabled=True,
                    cultivation_enabled=True,
                    retail_enabled=False,
                ),
                Facility(
                    id="facility-destination",
                    organization_id="org-recall",
                    name="Retail License",
                    code="RTL",
                    license_number="RTL-001",
                    production_enabled=False,
                    cultivation_enabled=False,
                    retail_enabled=True,
                ),
                Facility(
                    id="facility-other",
                    organization_id="org-other",
                    name="Other Tenant Facility",
                    code="OTH",
                    license_number="OTH-001",
                    production_enabled=True,
                ),
            ]
        )
        products = [
            Product(id="product-raw", organization_id="org-recall", sku="RAW", name="Raw Material", item_type="cannabis", base_unit="g", unit_cost=1.0),
            Product(id="product-mid", organization_id="org-recall", sku="MID", name="Intermediate", item_type="cannabis", base_unit="g", unit_cost=2.0),
            Product(id="product-finished", organization_id="org-recall", sku="FIN", name="Finished Product", item_type="cannabis", base_unit="g", unit_cost=3.0),
            Product(id="product-byproduct", organization_id="org-recall", sku="BYP", name="Byproduct", item_type="cannabis", base_unit="g", unit_cost=0.5),
        ]
        session.add_all(products)
        session.flush()
        _lot(session, "lot-upstream", "UPSTREAM", "PKG-UPSTREAM", "product-raw", 20.0)
        _lot(session, "lot-source", "SOURCE", "PKG-SOURCE", "product-raw", 100.0)
        _lot(session, "lot-mid", "MID", "PKG-MID", "product-mid", 30.0)
        _lot(session, "lot-finished", "FINISHED", "PKG-FINISHED", "product-finished", 10.0)
        _lot(session, "lot-byproduct", "BYPRODUCT", "PKG-BYPRODUCT", "product-byproduct", 5.0)

        upstream = MaterialLineageService.transformation(
            session,
            organization_id="org-recall",
            facility_id="facility-source",
            transformation_type="upstream_process",
            source_entity_type="manual",
            source_entity_id="upstream-process",
            actor="seed",
        )
        MaterialLineageService.add_input(
            session,
            upstream,
            entity_type="lot",
            entity_id="lot-upstream",
            lot_id="lot-upstream",
            product_id="product-raw",
            quantity=10.0,
            unit="g",
        )
        MaterialLineageService.add_output(
            session,
            upstream,
            lot_id="lot-source",
            product_id="product-raw",
            quantity=9.0,
            unit="g",
        )

        first = MaterialLineageService.transformation(
            session,
            organization_id="org-recall",
            facility_id="facility-source",
            transformation_type="extraction",
            source_entity_type="manual",
            source_entity_id="extraction-1",
            actor="seed",
        )
        MaterialLineageService.add_input(
            session,
            first,
            entity_type="lot",
            entity_id="lot-source",
            lot_id="lot-source",
            product_id="product-raw",
            quantity=40.0,
            unit="g",
        )
        MaterialLineageService.add_output(
            session,
            first,
            lot_id="lot-mid",
            product_id="product-mid",
            quantity=30.0,
            unit="g",
        )
        MaterialLineageService.add_output(
            session,
            first,
            lot_id="lot-byproduct",
            product_id="product-byproduct",
            quantity=5.0,
            unit="g",
            purpose="recoverable_material",
        )

        second = MaterialLineageService.transformation(
            session,
            organization_id="org-recall",
            facility_id="facility-source",
            transformation_type="packaging",
            source_entity_type="manual",
            source_entity_id="packaging-1",
            actor="seed",
        )
        MaterialLineageService.add_input(
            session,
            second,
            entity_type="lot",
            entity_id="lot-mid",
            lot_id="lot-mid",
            product_id="product-mid",
            quantity=20.0,
            unit="g",
        )
        MaterialLineageService.add_output(
            session,
            second,
            lot_id="lot-finished",
            product_id="product-finished",
            quantity=10.0,
            unit="g",
        )

        # Deliberately add a graph cycle to prove Recall 360 traversal is cycle-safe.
        cycle = MaterialLineageService.transformation(
            session,
            organization_id="org-recall",
            facility_id="facility-source",
            transformation_type="rework_cycle_fixture",
            source_entity_type="manual",
            source_entity_id="cycle-fixture",
            actor="seed",
        )
        MaterialLineageService.add_input(
            session,
            cycle,
            entity_type="lot",
            entity_id="lot-finished",
            lot_id="lot-finished",
            product_id="product-finished",
            quantity=1.0,
            unit="g",
        )
        MaterialLineageService.add_output(
            session,
            cycle,
            lot_id="lot-source",
            product_id="product-raw",
            quantity=1.0,
            unit="g",
            purpose="rework",
        )
    return engine


def _lot(session: Session, lot_id: str, lot_code: str, package_id: str, product_id: str, quantity: float) -> None:
    session.add(
        InventoryLot(
            id=lot_id,
            organization_id="org-recall",
            facility_id="facility-source",
            product_id=product_id,
            lot_code=lot_code,
            compliance_package_id=package_id,
            external_inventory_id=package_id,
            barcode_value=package_id,
            location_code="VAULT",
            status="released",
        )
    )
    session.flush()
    session.add(
        InventoryTransaction(
            organization_id="org-recall",
            facility_id="facility-source",
            lot_id=lot_id,
            transaction_type="receipt",
            quantity_delta=quantity,
            unit="g",
            actor="seed",
        )
    )


def _transfer_finished(engine):
    transfers = InventoryTransferService(engine)
    dispatched = transfers.dispatch(
        "org-recall",
        "facility-source",
        destination_facility_id="facility-destination",
        manifest_reference="RECALL-MANIFEST-001",
        lines=[{"source_lot_id": "lot-finished", "quantity": 4.0}],
        actor="shipper",
    )
    received = transfers.receive_line(
        "org-recall",
        "facility-destination",
        dispatched["id"],
        dispatched["lines"][0]["id"],
        operation="retail",
        package_id="PKG-RETAIL-FINISHED",
        lot_code="RETAIL-FINISHED",
        actor="receiver",
    )
    return received["lines"][0]["destination_lot_id"]


def _headers(facility_id: str, role: str = "operator", organization_id: str = "org-recall") -> dict[str, str]:
    return {
        "X-Organization-Id": organization_id,
        "X-Facility-Id": facility_id,
        "X-User-Id": f"{role}-{facility_id}",
        "X-User-Role": role,
    }


def test_recall_360_walks_only_downstream_branches_and_is_cycle_safe():
    engine = _engine()
    destination_lot_id = _transfer_finished(engine)
    recall = RecallBlastRadiusService(engine).blast_radius(
        organization_id="org-recall",
        facility_id="facility-source",
        lot_id="lot-source",
        allowed_facility_ids={"facility-source", "facility-destination"},
    )
    ids = {row["lot_id"] for row in recall["affected_lots"]}
    assert ids == {"lot-source", "lot-mid", "lot-finished", "lot-byproduct", destination_lot_id}
    assert "lot-upstream" not in ids
    assert recall["affected_lot_count"] == 5
    assert recall["downstream_lot_count"] == 4
    assert recall["facility_count"] == 2
    assert recall["license_count"] == 2
    assert recall["transfer_count"] == 1
    assert recall["protected_exposure_count"] == 0
    assert recall["cross_facility"] is True
    source = next(row for row in recall["affected_lots"] if row["lot_id"] == "lot-source")
    assert source["is_source"] is True
    assert source["path"] == []
    destination = next(row for row in recall["affected_lots"] if row["lot_id"] == destination_lot_id)
    relationships = [edge["relationship"] for edge in destination["path"]]
    assert relationships[-2:] == ["transferred_out", "received_as_transfer"]


def test_recall_360_fails_closed_across_unassigned_facilities_without_hiding_exposure():
    engine = _engine()
    destination_lot_id = _transfer_finished(engine)
    recall = RecallBlastRadiusService(engine).blast_radius(
        organization_id="org-recall",
        facility_id="facility-source",
        lot_id="lot-source",
        allowed_facility_ids={"facility-source"},
    )
    ids = {row["lot_id"] for row in recall["affected_lots"]}
    assert destination_lot_id not in ids
    assert recall["facility_count"] == 1
    assert recall["transfer_count"] == 1
    assert recall["redacted_facility_count"] == 1
    assert recall["protected_exposure_count"] == 1
    exposure = recall["protected_exposures"][0]
    assert exposure["redacted"] is True
    assert exposure["package_id"] == "PKG-RETAIL-FINISHED"
    assert exposure["license_number"] == "RTL-001"
    assert exposure["path"][-1]["relationship"] == "received_as_transfer"


def test_recall_360_does_not_treat_cancelled_transfer_as_live_exposure():
    engine = _engine()
    transfers = InventoryTransferService(engine)
    dispatched = transfers.dispatch(
        "org-recall",
        "facility-source",
        destination_facility_id="facility-destination",
        manifest_reference="RECALL-CANCELLED-001",
        lines=[{"source_lot_id": "lot-byproduct", "quantity": 2.0}],
        actor="shipper",
    )
    cancelled = transfers.cancel(
        "org-recall",
        "facility-source",
        dispatched["id"],
        actor="shipper",
        reason="Manifest cancelled before departure",
    )
    assert cancelled["status"] == "cancelled"

    recall = RecallBlastRadiusService(engine).blast_radius(
        organization_id="org-recall",
        facility_id="facility-source",
        lot_id="lot-source",
        allowed_facility_ids={"facility-source"},
    )
    assert recall["transfer_count"] == 0
    assert recall["protected_exposure_count"] == 0
    assert recall["redacted_facility_count"] == 0
    assert recall["cross_facility"] is False


def test_recall_360_api_uses_facility_scope_and_rejects_cross_tenant_source():
    engine = _engine()
    destination_lot_id = _transfer_finished(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    try:
        operator = client.get(
            "/api/v1/material-lineage/lots/lot-source/recall",
            headers=_headers("facility-source", role="operator"),
        )
        assert operator.status_code == 200, operator.text
        operator_data = operator.json()
        assert destination_lot_id not in {row["lot_id"] for row in operator_data["affected_lots"]}
        assert operator_data["protected_exposure_count"] == 1

        admin = client.get(
            "/api/v1/material-lineage/lots/lot-source/recall",
            headers=_headers("facility-source", role="admin"),
        )
        assert admin.status_code == 200, admin.text
        assert destination_lot_id in {row["lot_id"] for row in admin.json()["affected_lots"]}

        other_tenant = client.get(
            "/api/v1/material-lineage/lots/lot-source/recall",
            headers=_headers("facility-other", role="admin", organization_id="org-other"),
        )
        assert other_tenant.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_recall_360_is_visible_in_package_360_and_explicitly_read_only():
    package_window = (ROOT / "frontend/src/components/Package360Window.tsx").read_text(encoding="utf-8")
    recall_surface = (ROOT / "frontend/src/components/RecallBlastRadius.tsx").read_text(encoding="utf-8")
    router = (ROOT / "backend/app/routers/production_mutations.py").read_text(encoding="utf-8")

    assert "RecallBlastRadius" in package_window
    assert "RECALL 360 · BLAST RADIUS" in recall_surface
    assert "/api/v1/material-lineage/lots/${lotId}/recall" in recall_surface
    assert "read-only analysis" in recall_surface
    assert "does not place inventory on hold, change Metrc or notify a regulator" in recall_surface
    assert '@lineage_router.get("/lots/{lot_id}/recall")' in router
