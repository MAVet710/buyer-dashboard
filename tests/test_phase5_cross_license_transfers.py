from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.inventory_quality.service import LotQualityService
from modules.inventory_transfers.lineage import CrossFacilityLineageService
from modules.inventory_transfers.models import InventoryTransfer
from modules.inventory_transfers.service import InventoryTransferService

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
                Organization(id="org-transfer", name="Transfer Org", slug="transfer-org"),
                Organization(id="org-other", name="Other Org", slug="other-org"),
            ]
        )
        session.add_all(
            [
                Facility(
                    id="facility-source",
                    organization_id="org-transfer",
                    name="Cultivation & Manufacturing",
                    code="SRC",
                    license_number="SRC-LIC-001",
                    license_type="Marijuana Cultivator / Product Manufacturer",
                    retail_enabled=False,
                    production_enabled=True,
                    cultivation_enabled=True,
                ),
                Facility(
                    id="facility-destination",
                    organization_id="org-transfer",
                    name="Retail Store",
                    code="DST",
                    license_number="DST-LIC-001",
                    license_type="Marijuana Retailer",
                    retail_enabled=True,
                    production_enabled=False,
                    cultivation_enabled=False,
                ),
                Facility(
                    id="facility-third",
                    organization_id="org-transfer",
                    name="Second Manufacturing License",
                    code="THIRD",
                    license_number="THIRD-LIC-001",
                    retail_enabled=False,
                    production_enabled=True,
                ),
                Facility(
                    id="facility-other",
                    organization_id="org-other",
                    name="Other Tenant",
                    code="OTHER",
                    license_number="OTHER-LIC",
                    production_enabled=True,
                ),
            ]
        )
        product = Product(
            id="product-flower",
            organization_id="org-transfer",
            sku="FLOWER-XFER",
            name="Transfer Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=2.5,
        )
        session.add(product)
        session.flush()
        for lot_id, lot_code, package_id, quantity in (
            ("source-lot-1", "SRC-LOT-001", "PKG-SRC-001", 100.0),
            ("source-lot-2", "SRC-LOT-002", "PKG-SRC-002", 50.0),
        ):
            lot = InventoryLot(
                id=lot_id,
                organization_id="org-transfer",
                facility_id="facility-source",
                product_id=product.id,
                lot_code=lot_code,
                compliance_package_id=package_id,
                external_inventory_id=package_id,
                barcode_value=package_id,
                location_code="VAULT",
                status="released",
            )
            session.add(lot)
            session.flush()
            session.add(
                InventoryTransaction(
                    organization_id="org-transfer",
                    facility_id="facility-source",
                    lot_id=lot.id,
                    transaction_type="receipt",
                    quantity_delta=quantity,
                    unit="g",
                    actor="seed",
                )
            )
        LotQualityService.set_evidence(
            session,
            lot_id="source-lot-1",
            lab_testing_state="Passed",
            coa_reference="COA-XFER-001",
            coa_url="https://example.test/coa-xfer-001.pdf",
            thca_percent=24.2,
            tac_percent=26.1,
            total_terpenes_percent=2.4,
            evidence_source="lab",
            actor="qa",
        )
    return engine


def _balance(session: Session, lot_id: str) -> float:
    return float(
        session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == lot_id
            )
        )
        or 0.0
    )


def _headers(facility_id: str, role: str = "operator") -> dict[str, str]:
    return {
        "X-Organization-Id": "org-transfer",
        "X-Facility-Id": facility_id,
        "X-User-Id": f"{role}-{facility_id}",
        "X-User-Role": role,
    }


def test_dispatch_and_receipt_keep_license_ledgers_separate_and_copy_coa_evidence():
    engine = _engine()
    service = InventoryTransferService(engine)
    transfer = service.dispatch(
        "org-transfer",
        "facility-source",
        destination_facility_id="facility-destination",
        manifest_reference="MANIFEST-001",
        lines=[{"source_lot_id": "source-lot-1", "quantity": 40.0}],
        actor="shipper",
    )
    line = transfer["lines"][0]
    assert transfer["status"] == "shipped"
    assert transfer["source_license_number"] == "SRC-LIC-001"
    assert transfer["destination_license_number"] == "DST-LIC-001"
    assert line["destination_lot_id"] is None

    with Session(engine) as session:
        assert _balance(session, "source-lot-1") == pytest.approx(60.0)
        assert session.scalar(
            select(func.count(InventoryLot.id)).where(InventoryLot.facility_id == "facility-destination")
        ) == 0
        source_tx = session.get(InventoryTransaction, line["source_transaction_id"])
        assert source_tx.transaction_type == "transfer_out"
        assert source_tx.facility_id == "facility-source"
        assert source_tx.quantity_delta == pytest.approx(-40.0)

    received = service.receive_line(
        "org-transfer",
        "facility-destination",
        transfer["id"],
        line["id"],
        operation="retail",
        package_id="PKG-DST-001",
        lot_code="DST-LOT-001",
        location="RECEIVING",
        actor="receiver",
    )
    received_line = received["lines"][0]
    assert received["status"] == "received"
    assert received_line["destination_lot_id"]

    with Session(engine) as session:
        assert _balance(session, "source-lot-1") == pytest.approx(60.0)
        assert _balance(session, received_line["destination_lot_id"]) == pytest.approx(40.0)
        destination = session.get(InventoryLot, received_line["destination_lot_id"])
        assert destination.facility_id == "facility-destination"
        assert destination.compliance_package_id == "PKG-DST-001"
        dest_tx = session.get(InventoryTransaction, received_line["destination_transaction_id"])
        assert dest_tx.transaction_type == "transfer_in"
        assert dest_tx.facility_id == "facility-destination"
        assert dest_tx.quantity_delta == pytest.approx(40.0)
        evidence = LotQualityService.read(session, destination.id)
        assert evidence is not None
        assert evidence.lab_testing_state == "Passed"
        assert evidence.coa_reference == "COA-XFER-001"
        assert evidence.coa_url == "https://example.test/coa-xfer-001.pdf"
        assert evidence.evidence_source == "inherited:facility_transfer"
        assert evidence.inherited_from_lot_id == "source-lot-1"


def test_partial_receipt_blocks_cancellation_until_a_return_transfer_is_created():
    engine = _engine()
    service = InventoryTransferService(engine)
    transfer = service.dispatch(
        "org-transfer",
        "facility-source",
        destination_facility_id="facility-destination",
        manifest_reference="MANIFEST-PARTIAL",
        lines=[
            {"source_lot_id": "source-lot-1", "quantity": 25.0},
            {"source_lot_id": "source-lot-2", "quantity": 20.0},
        ],
        actor="shipper",
    )
    first, second = transfer["lines"]
    partially_received = service.receive_line(
        "org-transfer",
        "facility-destination",
        transfer["id"],
        first["id"],
        operation="retail",
        package_id="PKG-DST-P1",
        lot_code="DST-P1",
        actor="receiver",
    )
    assert partially_received["status"] == "partially_received"
    with pytest.raises(ValueError, match="return transfer"):
        service.cancel(
            "org-transfer",
            "facility-source",
            transfer["id"],
            actor="shipper",
            reason="Cannot undo material already received",
        )
    completed = service.receive_line(
        "org-transfer",
        "facility-destination",
        transfer["id"],
        second["id"],
        operation="retail",
        package_id="PKG-DST-P2",
        lot_code="DST-P2",
        actor="receiver",
    )
    assert completed["status"] == "received"
    assert {row["status"] for row in completed["lines"]} == {"received"}


def test_unreceived_transfer_cancellation_restores_source_exactly_without_destination_inventory():
    engine = _engine()
    service = InventoryTransferService(engine)
    transfer = service.dispatch(
        "org-transfer",
        "facility-source",
        destination_facility_id="facility-destination",
        manifest_reference="MANIFEST-CANCEL",
        lines=[{"source_lot_id": "source-lot-1", "quantity": 30.0}],
        actor="shipper",
    )
    with Session(engine) as session:
        assert _balance(session, "source-lot-1") == pytest.approx(70.0)
    cancelled = service.cancel(
        "org-transfer",
        "facility-source",
        transfer["id"],
        actor="shipper",
        reason="Truck did not depart",
    )
    assert cancelled["status"] == "cancelled"
    with Session(engine) as session:
        assert _balance(session, "source-lot-1") == pytest.approx(100.0)
        tx_types = list(
            session.scalars(
                select(InventoryTransaction.transaction_type).where(
                    InventoryTransaction.lot_id == "source-lot-1"
                )
            )
        )
        assert "transfer_out" in tx_types
        assert "transfer_cancel_return" in tx_types
        assert session.scalar(
            select(func.count(InventoryLot.id)).where(InventoryLot.facility_id == "facility-destination")
        ) == 0


def test_transfer_scope_rejects_cross_tenant_destination_and_source_lot_from_wrong_facility_without_mutation():
    engine = _engine()
    service = InventoryTransferService(engine)
    with pytest.raises(ValueError, match="Destination facility was not found"):
        service.dispatch(
            "org-transfer",
            "facility-source",
            destination_facility_id="facility-other",
            manifest_reference="MANIFEST-BAD-ORG",
            lines=[{"source_lot_id": "source-lot-1", "quantity": 10.0}],
            actor="shipper",
        )
    with pytest.raises(ValueError, match="source packages were not found"):
        service.dispatch(
            "org-transfer",
            "facility-third",
            destination_facility_id="facility-destination",
            manifest_reference="MANIFEST-BAD-SOURCE",
            lines=[{"source_lot_id": "source-lot-1", "quantity": 10.0}],
            actor="shipper",
        )
    with Session(engine) as session:
        assert _balance(session, "source-lot-1") == pytest.approx(100.0)
        assert session.scalar(select(func.count(InventoryTransfer.id))) == 0


def test_transfer_api_requires_state_system_confirmation_and_write_role_before_ledger_mutation():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    try:
        request = {
            "destination_facility_id": "facility-destination",
            "manifest_reference": "MANIFEST-API",
            "external_transfer_id": "METRC-XFER-API",
            "state_transfer_confirmed": False,
            "lines": [{"source_lot_id": "source-lot-1", "quantity": 15.0}],
        }
        unconfirmed = client.post(
            "/api/v1/inventory/transfers/dispatch",
            headers=_headers("facility-source"),
            json=request,
        )
        assert unconfirmed.status_code == 422, unconfirmed.text
        forbidden = client.post(
            "/api/v1/inventory/transfers/dispatch",
            headers=_headers("facility-source", role="read_only"),
            json={**request, "state_transfer_confirmed": True},
        )
        assert forbidden.status_code == 403, forbidden.text
        with Session(engine) as session:
            assert _balance(session, "source-lot-1") == pytest.approx(100.0)

        dispatched = client.post(
            "/api/v1/inventory/transfers/dispatch",
            headers=_headers("facility-source"),
            json={**request, "state_transfer_confirmed": True},
        )
        assert dispatched.status_code == 201, dispatched.text
        transfer = dispatched.json()
        line = transfer["lines"][0]
        with Session(engine) as session:
            assert _balance(session, "source-lot-1") == pytest.approx(85.0)

        receive_request = {
            "operation": "retail",
            "lot_code": "DST-API-LOT",
            "package_id": "PKG-DST-API",
            "location": "RECEIVING",
            "state_receipt_confirmed": False,
        }
        unconfirmed_receipt = client.post(
            f"/api/v1/inventory/transfers/{transfer['id']}/lines/{line['id']}/receive",
            headers=_headers("facility-destination"),
            json=receive_request,
        )
        assert unconfirmed_receipt.status_code == 422, unconfirmed_receipt.text
        with Session(engine) as session:
            assert session.scalar(
                select(func.count(InventoryLot.id)).where(InventoryLot.facility_id == "facility-destination")
            ) == 0

        received = client.post(
            f"/api/v1/inventory/transfers/{transfer['id']}/lines/{line['id']}/receive",
            headers=_headers("facility-destination"),
            json={**receive_request, "state_receipt_confirmed": True},
        )
        assert received.status_code == 200, received.text
        assert received.json()["status"] == "received"

        cancel_dispatch = client.post(
            "/api/v1/inventory/transfers/dispatch",
            headers=_headers("facility-source"),
            json={
                "destination_facility_id": "facility-destination",
                "manifest_reference": "MANIFEST-API-CANCEL",
                "state_transfer_confirmed": True,
                "lines": [{"source_lot_id": "source-lot-2", "quantity": 10.0}],
            },
        )
        assert cancel_dispatch.status_code == 201, cancel_dispatch.text
        cancel_transfer = cancel_dispatch.json()
        unconfirmed_cancel = client.post(
            f"/api/v1/inventory/transfers/{cancel_transfer['id']}/cancel",
            headers=_headers("facility-source"),
            json={"reason": "Manifest cancelled", "state_cancel_confirmed": False},
        )
        assert unconfirmed_cancel.status_code == 422, unconfirmed_cancel.text
        with Session(engine) as session:
            assert _balance(session, "source-lot-2") == pytest.approx(40.0)
        confirmed_cancel = client.post(
            f"/api/v1/inventory/transfers/{cancel_transfer['id']}/cancel",
            headers=_headers("facility-source"),
            json={"reason": "Manifest cancelled", "state_cancel_confirmed": True},
        )
        assert confirmed_cancel.status_code == 200, confirmed_cancel.text
        assert confirmed_cancel.json()["status"] == "cancelled"
        with Session(engine) as session:
            assert _balance(session, "source-lot-2") == pytest.approx(50.0)
    finally:
        app.dependency_overrides.clear()


def test_cross_facility_lineage_federates_only_authorized_facilities_and_redacts_the_rest():
    engine = _engine()
    service = InventoryTransferService(engine)
    transfer = service.dispatch(
        "org-transfer",
        "facility-source",
        destination_facility_id="facility-destination",
        manifest_reference="MANIFEST-LINEAGE",
        lines=[{"source_lot_id": "source-lot-1", "quantity": 12.0}],
        actor="shipper",
    )
    received = service.receive_line(
        "org-transfer",
        "facility-destination",
        transfer["id"],
        transfer["lines"][0]["id"],
        operation="retail",
        package_id="PKG-DST-LINEAGE",
        lot_code="DST-LINEAGE",
        actor="receiver",
    )
    destination_lot_id = received["lines"][0]["destination_lot_id"]
    lineage = CrossFacilityLineageService(engine)

    authorized = lineage.lot_graph(
        organization_id="org-transfer",
        facility_id="facility-destination",
        lot_id=destination_lot_id,
        allowed_facility_ids={"facility-source", "facility-destination"},
    )
    assert authorized["cross_facility"] is True
    assert authorized["transfer_count"] == 1
    assert authorized["redacted_facility_count"] == 0
    assert any(node["key"] == "lot:source-lot-1" for node in authorized["nodes"])
    relationships = {edge["relationship"] for edge in authorized["edges"]}
    assert {"transferred_out", "received_as_transfer"}.issubset(relationships)

    restricted = lineage.lot_graph(
        organization_id="org-transfer",
        facility_id="facility-destination",
        lot_id=destination_lot_id,
        allowed_facility_ids={"facility-destination"},
    )
    assert restricted["cross_facility"] is True
    assert restricted["redacted_facility_count"] == 1
    assert not any(node["key"] == "lot:source-lot-1" for node in restricted["nodes"])
    assert any(
        node.get("type") == "transfer_reference"
        and node.get("redacted") is True
        and node.get("package_id") == "PKG-SRC-001"
        for node in restricted["nodes"]
    )


def test_transfers_are_first_class_inventory_workspaces_and_contextual_inventory_actions():
    routes = (ROOT / "frontend/src/lib/workspaceRoutes.ts").read_text(encoding="utf-8")
    shell = (ROOT / "frontend/src/components/AppShell.tsx").read_text(encoding="utf-8")
    app_source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    inventory = (ROOT / "frontend/src/pages/InventoryPage.tsx").read_text(encoding="utf-8")
    receive_history = (ROOT / "frontend/src/components/ReceiveHistory.tsx").read_text(encoding="utf-8")
    transfers = (ROOT / "frontend/src/components/InventoryTransferManager.tsx").read_text(encoding="utf-8")

    assert 'path: "/inventory/transfers"' in routes
    assert 'path: "/production/inventory/transfers"' in routes
    assert 'label: "Transfers", page: "Retail Inventory Transfers"' in shell
    assert 'label: "Transfers", page: "Production Inventory Transfers"' in shell
    assert 'page === "Retail Inventory Transfers"' in app_source
    assert 'page === "Production Inventory Transfers"' in app_source
    assert "InventoryTransferManager" in inventory
    assert 'ariaLabel="Inventory license transfer"' in inventory
    assert 'className="transfer-workspace-window"' in inventory
    assert "selectedPackages" in inventory
    assert "blockedTransferPackages" in inventory
    assert "transferSelectionReady" in inventory
    assert "Retail Inventory Transfers" in inventory
    assert "Production Inventory Transfers" in inventory
    assert "InventoryTransferManager" not in receive_history
    assert "License transfers" not in receive_history
    assert "state-system/Metrc transfer" in transfers
    assert "accepted/received in the required state system" in transfers
    assert "state-system/Metrc transfer cancellation" in transfers
