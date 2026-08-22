from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import (
    Base,
    Facility,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Organization,
    Product,
    ProductionOrder,
    TradePartner,
    CommercialOrder,
    CommercialOrderLine,
    AppUser,
    AppUserFacilityRole,
    LegalAcceptanceEvent,
)
from backend.app.config import Settings, get_settings
from backend.app.auth import get_authorization_engine
from modules.integrations.models import IntegrationConfiguration


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(id="org-1", name="Buyer Dash", slug="buyer-dash")
        facility = Facility(id="facility-1", organization_id=organization.id, name="Boston Production", code="BOS", cultivation_enabled=True)
        product = Product(
            id="product-1",
            organization_id=organization.id,
            sku="BD-BULK",
            name="Blue Dream Bulk Flower",
            item_type="cannabis",
            base_unit="g",
        )
        lot = InventoryLot(
            id="lot-1",
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="LOT-100",
            compliance_package_id="1A406000000001",
            location_code="Bulk Vault",
            status="available",
        )
        order = ProductionOrder(
            id="order-1",
            organization_id=organization.id,
            facility_id=facility.id,
            order_number="PO-1",
            work_type="internal",
            product_name="Blue Dream Extract",
            sku="BD-EXT",
            product_format="bulk extract",
            requested_units=10,
            due_at=None,
            priority="normal",
            status="scheduled",
            notes="",
            created_by="tester",
            updated_by="tester",
        )
        session.add_all((organization, facility, product, lot, order))
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receive",
                quantity_delta=100,
                unit="g",
                reason="Initial receipt",
                reference="MAN-1",
                actor="tester",
            )
        )
        session.add(
            MaterialReservation(
                organization_id=organization.id,
                facility_id=facility.id,
                production_order_id=order.id,
                lot_id=lot.id,
                quantity=15,
                unit="g",
                status="reserved",
                reserved_by="tester",
            )
        )
        session.commit()
    return engine


def test_retail_and_production_read_the_same_durable_package_ledger():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1"}
    try:
        production = client.get("/api/v1/inventory/production/packages", headers=headers)
        retail = client.get("/api/v1/inventory/retail/packages", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert production.status_code == 200
    assert retail.status_code == 200
    assert production.json()["operation"] == "production"
    assert retail.json()["operation"] == "retail"
    for payload in (production.json(), retail.json()):
        assert payload["summary"]["available_quantity"] == 100
        assert payload["summary"]["reserved_quantity"] == 15
        assert payload["items"][0]["usable"] == 85
        assert payload["items"][0]["package_id"] == "1A406000000001"


def test_facility_capabilities_are_exposed_and_enforced_by_inventory_routes():
    engine = _engine()
    with Session(engine) as session:
        facility = session.get(Facility, "facility-1")
        facility.retail_enabled = True
        facility.production_enabled = False
        facility.cultivation_enabled = False
        facility.commercial_enabled = True
        facility.license_number = "RETAIL-001"
        facility.license_type = "retailer"
        session.commit()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "local-developer", "X-User-Role": "dev"}
    try:
        context = client.get("/api/v1/account/context", headers=headers)
        retail = client.get("/api/v1/inventory/retail/packages", headers=headers)
        production = client.get("/api/v1/inventory/production/packages", headers=headers)
        plants = client.get("/api/v1/inventory/production/plants", headers=headers)
        retail_catalog = client.get("/api/v1/product-master?operation=retail", headers=headers)
        production_catalog = client.get("/api/v1/product-master?operation=production", headers=headers)
        cross_scope_create = client.post("/api/v1/product-master", headers=headers, json={"sku": "PROD-DENIED", "name": "Production material", "item_type": "cannabis", "retail_enabled": False, "production_enabled": True})
    finally:
        app.dependency_overrides.clear()
    assert context.status_code == 200
    assert context.json()["facility"]["license_number"] == "RETAIL-001"
    assert context.json()["capabilities"] == {"retail": True, "production": False, "cultivation": False, "commercial": True}
    assert retail.status_code == 200
    assert production.status_code == 403
    assert plants.status_code == 403
    assert retail_catalog.status_code == 200
    assert production_catalog.status_code == 403
    assert cross_scope_create.status_code == 403


def test_inventory_requires_facility_context():
    client = TestClient(app)
    response = client.get("/api/v1/inventory/production/packages")
    assert response.status_code == 400


def test_retail_receipt_posts_atomically_to_shared_ledger_and_history():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {
        "X-Organization-Id": "org-1",
        "X-Facility-Id": "facility-1",
        "X-User-Id": "receiver@example.com",
    }
    payload = {
        "product_id": "product-1",
        "package_id": "1A406000000002",
        "lot_code": "LOT-200",
        "quantity": 24,
        "unit": "g",
        "location": "Retail Vault",
        "source_name": "Atlantic Cultivation",
        "manifest_reference": "MAN-200",
        "lab_testing_state": "TestPassed",
        "coa_reference": "COA-200",
    }
    try:
        receipt = client.post("/api/v1/inventory/retail/receipts", headers=headers, json=payload)
        duplicate = client.post("/api/v1/inventory/retail/receipts", headers=headers, json=payload)
        inventory = client.get("/api/v1/inventory/retail/packages", headers=headers)
        history = client.get("/api/v1/inventory/retail/receive-history", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert receipt.status_code == 201
    assert receipt.json()["operation"] == "retail"
    assert duplicate.status_code == 409
    received = next(item for item in inventory.json()["items"] if item["package_id"] == payload["package_id"])
    assert received["available"] == 24
    assert received["location"] == "Retail Vault"
    event = next(item for item in history.json() if item["package_id"] == payload["package_id"])
    assert event["manifest_reference"] == "MAN-200"
    assert event["source_name"] == "Atlantic Cultivation"
    assert event["actor"] == "receiver@example.com"


def test_unpassed_receipt_enters_hold_inventory():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1"}
    try:
        response = client.post(
            "/api/v1/inventory/production/receipts",
            headers=headers,
            json={
                "product_id": "product-1",
                "package_id": "HOLD-1",
                "quantity": 50,
                "unit": "g",
                "lab_testing_state": "TestingInProgress",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json()["status"] == "hold"


def test_retail_sales_import_is_durable_idempotent_and_audited():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "buyer@example.com"}
    payload = {
        "source_system": "Dutchie",
        "import_batch_id": "sales-2026-08-21",
        "lines": [{
            "source_record_id": "sale-line-1",
            "sold_at": "2026-08-21T15:00:00Z",
            "quantity": 3,
            "product_id": "product-1",
            "sku": "BD-BULK",
            "product_name": "Blue Dream Bulk Flower",
            "net_sales": 90,
        }],
    }
    try:
        first = client.post("/api/v1/inventory/retail/sales/import", headers=headers, json=payload)
        second = client.post("/api/v1/inventory/retail/sales/import", headers=headers, json=payload)
        inventory = client.get("/api/v1/inventory/retail/packages", headers=headers)
    finally:
        app.dependency_overrides.clear()
    assert first.status_code == 201
    assert first.json() == {"imported": 1, "skipped_duplicates": 0, "unmapped_products": 0}
    assert second.status_code == 201
    assert second.json() == {"imported": 0, "skipped_duplicates": 1, "unmapped_products": 0}
    item = inventory.json()["items"][0]
    assert item["sold_30d"] == 3
    assert item["daily_velocity"] == 0.1
    assert item["days_on_hand"] == 1000


def test_adjustment_posts_correcting_transaction_and_protects_reservations():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "manager@example.com", "X-User-Role": "supervisor"}
    try:
        adjusted = client.post("/api/v1/inventory/production/adjustments", headers=headers, json={
            "lot_id": "lot-1", "adjustment_type": "set_quantity", "quantity": 90,
            "reason": "Inventory count correction", "reason_note": "Verified physical count",
        })
        invalid = client.post("/api/v1/inventory/production/adjustments", headers=headers, json={
            "lot_id": "lot-1", "adjustment_type": "set_quantity", "quantity": 10,
            "reason": "Inventory count correction",
        })
        inventory = client.get("/api/v1/inventory/production/packages", headers=headers)
    finally:
        app.dependency_overrides.clear()
    assert adjusted.status_code == 201
    assert adjusted.json()["previous_quantity"] == 100
    assert adjusted.json()["delta"] == -10
    assert adjusted.json()["final_quantity"] == 90
    assert invalid.status_code == 422
    assert "reserved" in invalid.json()["detail"]
    assert inventory.json()["items"][0]["available"] == 90


def test_adjustment_requires_authorized_role():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/inventory/retail/adjustments",
            headers={"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Role": "buyer"},
            json={"lot_id": "lot-1", "adjustment_type": "incremental", "quantity": 1, "reason": "Found inventory"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_react_audit_api_preserves_resumable_lifecycle_and_completion():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "counter@example.com", "X-User-Role": "supervisor"}
    try:
        created = client.post("/api/v1/inventory/retail/audits", headers=headers, json={
            "audit_number": "RTL-001", "scope_label": "Retail vault", "blind_count": True,
            "recount_tolerance": 10, "lot_ids": ["lot-1"],
        })
        audit_id = created.json()["id"]
        initial = client.get(f"/api/v1/inventory/retail/audits/{audit_id}", headers=headers)
        line_id = initial.json()["lines"][0]["id"]
        counted = client.post(f"/api/v1/inventory/retail/audits/{audit_id}/counts", headers=headers, json={"counts": [{"line_id": line_id, "counted_quantity": 95, "reason": "Physical count"}]})
        paused = client.post(f"/api/v1/inventory/retail/audits/{audit_id}/status", headers=headers, json={"status": "paused"})
        resumed = client.post(f"/api/v1/inventory/retail/audits/{audit_id}/status", headers=headers, json={"status": "in_progress"})
        completed = client.post(f"/api/v1/inventory/retail/audits/{audit_id}/complete", headers=headers, json={"post_adjustments": False})
    finally:
        app.dependency_overrides.clear()
    assert created.status_code == 201
    assert initial.json()["lines"][0]["expected_quantity"] is None
    assert counted.json()["lines"][0]["variance_quantity"] == -5
    assert counted.json()["lines"][0]["recount_required"] is False
    assert paused.json()["status"] == "paused"
    assert resumed.json()["status"] == "in_progress"
    assert completed.json()["status"] == "completed"


def test_production_plants_have_durable_lifecycle_and_facility_isolation():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "grower@example.com", "X-User-Role": "operator"}
    try:
        created = client.post("/api/v1/inventory/production/plants", headers=headers, json={"plant_tag": "PLANT-001", "strain_name": "Blue Dream", "phase": "clone", "room_code": "Clone Room"})
        plant_id = created.json()["id"]
        duplicate = client.post("/api/v1/inventory/production/plants", headers=headers, json={"plant_tag": "PLANT-001", "strain_name": "Blue Dream"})
        invalid = client.post(f"/api/v1/inventory/production/plants/{plant_id}/transition", headers=headers, json={"phase": "harvested", "reason": "Too early"})
        veg = client.post(f"/api/v1/inventory/production/plants/{plant_id}/transition", headers=headers, json={"phase": "vegetative", "room_code": "Veg 1", "reason": "Ready"})
        listing = client.get("/api/v1/inventory/production/plants?phase=vegetative", headers=headers)
        events = client.get(f"/api/v1/inventory/production/plants/{plant_id}/events", headers=headers)
        isolated = client.get("/api/v1/inventory/production/plants", headers={**headers, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()
    assert created.status_code == 201
    assert duplicate.status_code == 422
    assert invalid.status_code == 422
    assert veg.status_code == 200
    assert veg.json()["phase"] == "vegetative"
    assert veg.json()["room_code"] == "Veg 1"
    assert [item["plant_tag"] for item in listing.json()] == ["PLANT-001"]
    assert [event["event_type"] for event in events.json()] == ["created", "phase_changed", "room_moved"]
    assert isolated.status_code == 403


def test_production_execution_queue_and_events_use_existing_erp_ledger():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "operator@example.com", "X-User-Role": "operator"}
    try:
        queue = client.get("/api/v1/production/orders", headers=headers)
        started = client.post("/api/v1/production/orders/order-1/events", headers=headers, json={"event_type": "started", "notes": "Line cleared"})
        output = client.post("/api/v1/production/orders/order-1/outputs", headers=headers, json={"product_id": "product-1", "planned_quantity": 10, "unit": "g"})
        output_id = output.json()["id"]
        actual = client.post(f"/api/v1/production/outputs/{output_id}/actual", headers=headers, json={"actual_quantity": 8, "lot_code": "OUTPUT-1"})
        cost = client.post("/api/v1/production/orders/order-1/costs", headers=headers, json={"category": "labor", "amount_usd": 80})
        qa = client.post("/api/v1/production/orders/order-1/qa", headers={**headers, "X-User-Role": "qa"}, json={"event_type": "release", "result": "passed", "output_id": output_id})
        detail = client.get("/api/v1/production/orders/order-1", headers=headers)
        isolated = client.get("/api/v1/production/orders/order-1", headers={**headers, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()
    assert queue.status_code == 200
    assert queue.json()[0]["Order"] == "PO-1"
    assert started.status_code == 201
    assert output.status_code == 201
    assert actual.json()["status"] == "quarantine"
    assert cost.json()["amount_usd"] == 80
    assert qa.json()["result"] == "passed"
    assert detail.json()["order"]["status"] == "in_progress"
    assert detail.json()["events"][0]["notes"] == "Line cleared"
    assert detail.json()["outputs"][0]["status"] == "released"
    assert detail.json()["cogs"]["total"] == 80
    assert isolated.status_code == 403


def test_commercial_orders_are_tenant_safe_and_actionable():
    engine = _engine()
    with Session(engine) as session:
        partner = TradePartner(id="partner-1", organization_id="org-1", name="Retail Customer", partner_type="customer")
        order = CommercialOrder(id="sales-1", organization_id="org-1", facility_id="facility-1", partner_id=partner.id, order_number="SO-100", order_type="sales", created_by="seller", updated_by="seller")
        line = CommercialOrderLine(organization_id="org-1", commercial_order_id=order.id, product_id="product-1", position=1, description="Blue Dream", sku_snapshot="BD-BULK", quantity=5, unit="g", unit_price=20)
        session.add_all((partner, order, line)); session.commit()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "seller@example.com", "X-User-Role": "admin"}
    try:
        listing = client.get("/api/v1/commercial/orders", headers=headers)
        detail = client.get("/api/v1/commercial/orders/sales-1", headers=headers)
        confirmed = client.post("/api/v1/commercial/orders/sales-1/actions/confirm", headers=headers, json={})
        invoiced = client.post("/api/v1/commercial/orders/sales-1/invoices", headers=headers, json={"invoice_number": "INV-100", "due_days": 30})
        invoice_id = invoiced.json()["id"]
        sent = client.post(f"/api/v1/commercial/invoices/{invoice_id}/send", headers=headers, json={})
        paid = client.post(f"/api/v1/commercial/invoices/{invoice_id}/payments", headers=headers, json={"amount_usd": 40, "method": "ach", "reference": "ACH-1"})
        shipped = client.post("/api/v1/commercial/orders/sales-1/shipments", headers=headers, json={"shipment_number": "SHIP-100", "manifest_reference": "MAN-100"})
        ar = client.get("/api/v1/commercial/ar", headers=headers)
        isolated = client.get("/api/v1/commercial/orders/sales-1", headers={**headers, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()
    assert listing.status_code == 200
    assert listing.json()[0]["partner_name"] == "Retail Customer"
    assert listing.json()[0]["order_total"] == 100
    assert detail.json()["lines"][0]["sku_snapshot"] == "BD-BULK"
    assert confirmed.json()["status"] == "confirmed"
    assert invoiced.json()["total_usd"] == 100
    assert sent.json()["status"] == "sent"
    assert paid.json()["amount_usd"] == 40
    assert shipped.json()["status"] == "planned"
    assert ar.json()["total_ar"] == 60
    assert isolated.status_code == 403


def test_production_auth_uses_database_facility_role_not_spoofable_headers(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        user = AppUser(id="user-1", organization_id="org-1", username="operator", normalized_username="operator", display_name="Operator One", email="operator@example.com", password_hash="$2b$12$placeholder", role="operator", active=True, created_by="admin", updated_by="admin")
        role = AppUserFacilityRole(user_id=user.id, organization_id="org-1", facility_id="facility-1", role="qa")
        session.add_all((user, role)); session.commit()
    monkeypatch.setattr("backend.app.auth._decode_token", lambda token, settings: {"sub": "supabase-user", "email": "operator@example.com", "exp": 9999999999, "app_metadata": {"organization_id": "org-1", "facility_id": "facility-1"}})
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="production", database_url="sqlite://", supabase_jwks_url="https://example.invalid/jwks")
    client = TestClient(app)
    try:
        allowed = client.get("/api/v1/account/context", headers={"Authorization": "Bearer signed", "X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Role": "dev"})
        denied = client.get("/api/v1/account/context", headers={"Authorization": "Bearer signed", "X-Organization-Id": "org-1", "X-Facility-Id": "other-facility", "X-User-Role": "dev"})
    finally:
        app.dependency_overrides.clear()
    assert allowed.status_code == 200
    assert allowed.json()["user"]["role"] == "qa"
    assert denied.status_code == 403


def test_data_hub_upload_is_durable_versioned_and_facility_scoped():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "buyer@example.com", "X-User-Role": "admin"}
    csv = b"Product Name,Category,On Hand\nBlue Dream,Flower,42\n"
    try:
        uploaded = client.post("/api/v1/data-hub/datasets", headers=headers, data={"dataset_key": "inventory"}, files={"file": ("inventory.csv", csv, "text/csv")})
        listing = client.get("/api/v1/data-hub/datasets", headers=headers)
        isolated = client.get("/api/v1/data-hub/datasets", headers={**headers, "X-Facility-Id": "other-facility"})
        archived = client.post("/api/v1/data-hub/archive", headers=headers, json={})
    finally:
        app.dependency_overrides.clear()
    assert uploaded.status_code == 201
    assert uploaded.json()["quality"] == "Ready"
    assert uploaded.json()["row_count"] == 1
    assert listing.json()["history"][0]["status"] == "active"
    assert isolated.json()["history"] == []
    assert archived.json() == {"archived": 1}


def test_home_summary_and_universal_search_are_facility_scoped():
    engine = _engine()
    with Session(engine) as session:
        session.get(InventoryLot, "lot-1").status = "hold"
        session.get(ProductionOrder, "order-1").due_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1"}
    try:
        summary = client.get("/api/v1/home/summary", headers=headers)
        products = client.get("/api/v1/home/search?q=Blue", headers=headers)
        packages = client.get("/api/v1/home/search?q=1A406", headers=headers)
        inbox = client.get("/api/v1/home/inbox", headers=headers)
        product_360 = client.get("/api/v1/home/products/product-1", headers=headers)
        isolated = client.get("/api/v1/home/search?q=1A406", headers={**headers, "X-Facility-Id": "other-facility"})
        isolated_product = client.get("/api/v1/home/products/product-1", headers={**headers, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()
    assert summary.status_code == 200
    assert summary.json()["package_count"] == 1
    assert summary.json()["open_production"] == 1
    assert any(row["kind"] == "product" for row in products.json())
    assert packages.json()[0]["kind"] == "package"
    assert isolated.json() == []
    assert {row["area"] for row in inbox.json()["items"]} >= {"Inventory", "Production"}
    assert product_360.status_code == 200
    assert product_360.json()["inventory"]["on_hand"] == 100
    assert product_360.json()["inventory"]["packages"][0]["package_id"] == "1A406000000001"
    assert isolated_product.json()["inventory"]["packages"] == []


def test_doobie_actions_require_human_preview_and_database_role_approval():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    admin = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "admin@example.com", "X-User-Role": "admin"}
    buyer = {**admin, "X-User-Role": "buyer"}
    try:
        proposed = client.post("/api/v1/doobie/actions", headers=buyer, json={"action_type": "reserve_production_materials", "title": "Reserve Blue Dream inputs", "rationale": "Order is scheduled", "payload": {"production_order_id": "order-1"}, "preview": {"effect": "Reserve FIFO material lots"}, "idempotency_key": "recommendation-1"})
        proposal_id = proposed.json()["id"]
        blocked = client.post(f"/api/v1/doobie/actions/{proposal_id}/approve", headers=buyer, json={})
        approved = client.post(f"/api/v1/doobie/actions/{proposal_id}/approve", headers=admin, json={})
        listing = client.get("/api/v1/doobie/actions", headers=admin)
        isolated = client.get("/api/v1/doobie/actions", headers={**admin, "X-Facility-Id": "other-facility"})
    finally:
        app.dependency_overrides.clear()
    assert proposed.status_code == 201
    assert proposed.json()["status"] == "proposed"
    assert proposed.json()["preview"]["effect"] == "Reserve FIFO material lots"
    assert blocked.status_code == 403
    assert approved.json()["status"] == "approved"
    assert listing.json()["items"][0]["status"] == "approved"
    assert isolated.json()["items"] == []


def test_extraction_run_preserves_reservations_mass_balance_cogs_and_qa_gate():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "extractor@example.com", "X-User-Role": "qa"}
    try:
        created = client.post("/api/v1/extraction/runs", headers=headers, json={"batch_number": "EXT-100", "workflow_key": "bho_cured", "method": "BHO"})
        run_id = created.json()["id"]
        reserved = client.post(f"/api/v1/extraction/runs/{run_id}/inputs", headers=headers, json={"lot_id": "lot-1", "quantity": 20, "unit": "g"})
        input_id = reserved.json()["id"]
        consumed = client.post(f"/api/v1/extraction/inputs/{input_id}/consume", headers=headers, json={"quantity": 20})
        stage = client.post(f"/api/v1/extraction/runs/{run_id}/events", headers=headers, json={"stage_key": "intake", "event_type": "completed", "loss_weight_g": 2, "loss_reason": "Intake loss"})
        output = client.post(f"/api/v1/extraction/runs/{run_id}/outputs", headers=headers, json={"product_id": "product-1", "lot_code": "EXT-OUTPUT-1", "quantity": 8, "unit": "g"})
        output_id = output.json()["id"]
        coa = client.post(f"/api/v1/extraction/runs/{run_id}/qa", headers=headers, json={"event_type": "coa_attached", "result": "passed", "output_id": output_id, "coa_reference": "COA-1"})
        release = client.post(f"/api/v1/extraction/runs/{run_id}/qa", headers=headers, json={"event_type": "release", "result": "passed"})
        detail = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
        isolated = client.get(f"/api/v1/extraction/runs/{run_id}", headers={**headers, "X-Facility-Id": "other-facility"})
    finally: app.dependency_overrides.clear()
    assert created.status_code == 201
    assert consumed.json()["status"] == "consumed"
    assert stage.status_code == 201
    assert output.json()["status"] == "quarantine"
    assert coa.json()["result"] == "passed"
    assert release.json()["result"] == "passed"
    assert detail.json()["run"]["status"] == "complete"
    assert detail.json()["outputs"][0]["status"] == "released"
    assert detail.json()["mass_balance"]["consumed_input"] == 20
    assert detail.json()["mass_balance"]["recorded_output"] == 8
    assert isolated.status_code == 403


def test_product_master_is_one_catalog_with_retail_and_production_scopes():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "catalog@example.com", "X-User-Role": "admin"}
    try:
        created = client.post("/api/v1/product-master", headers=headers, json={"sku": "RETAIL-ONLY", "name": "Blue Dream 3.5g", "item_type": "finished_good", "base_unit": "unit", "upc": "012345678901", "retail_enabled": True, "production_enabled": False})
        product_id = created.json()["id"]
        profile = client.post(f"/api/v1/product-master/{product_id}/profile", headers=headers, json={"brand": "Doobie Logic", "category": "Flower", "subcategory": "Whole flower", "strain": "Blue Dream", "product_format": "3.5g jar", "retail_enabled": True, "production_enabled": False})
        alias = client.post(f"/api/v1/product-master/{product_id}/aliases", headers=headers, json={"alias": "Blue Dream Eighth", "source": "dutchie import"})
        mapping = client.post(f"/api/v1/product-master/{product_id}/mappings", headers=headers, json={"system_name": "dutchie", "external_id": "DUT-100", "external_name": "Blue Dream 3.5g"})
        value = client.post(f"/api/v1/product-master/{product_id}/values", headers=headers, json={"value_type": "retail_price", "amount": 35})
        retail = client.get("/api/v1/product-master?operation=retail", headers=headers)
        production = client.get("/api/v1/product-master?operation=production", headers=headers)
        duplicate_upc = client.post("/api/v1/product-master", headers=headers, json={"sku": "DUP", "name": "Duplicate", "item_type": "finished_good", "upc": "012345678901"})
        detail = client.get(f"/api/v1/product-master/{product_id}", headers=headers)
    finally: app.dependency_overrides.clear()
    assert created.status_code == 201
    assert profile.json()["profile"]["category"] == "Flower"
    assert alias.status_code == 201 and mapping.status_code == 201 and value.status_code == 201
    assert any(row["id"] == product_id for row in retail.json())
    assert all(row["id"] != product_id for row in production.json())
    assert duplicate_upc.status_code == 409
    assert detail.json()["mappings"][0]["external_id"] == "DUT-100"
    assert detail.json()["value_history"][0]["amount"] == 35


def test_purchase_order_receipt_atomically_creates_inventory_and_fulfills_line():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "buyer@example.com", "X-User-Role": "admin"}
    try:
        vendor = client.post("/api/v1/commercial/partners", headers=headers, json={"name": "Green Farm", "partner_type": "vendor", "license_or_registration": "LIC-1"})
        order = client.post("/api/v1/commercial/orders", headers=headers, json={"partner_id": vendor.json()["id"], "order_number": "PO-WEB-1", "order_type": "purchase", "lines": [{"product_id": "product-1", "quantity": 25, "unit": "g", "unit_price": 2.5}]})
        order_id = order.json()["id"]
        confirmed = client.post(f"/api/v1/commercial/orders/{order_id}/actions/confirm", headers=headers, json={})
        line_id = client.get(f"/api/v1/commercial/orders/{order_id}", headers=headers).json()["lines"][0]["id"]
        receipt = client.post(f"/api/v1/commercial/order-lines/{line_id}/receive", headers=headers, json={"lot_code": "PO-LOT-1", "package_id": "1A-PO-1", "quantity": 25, "location_code": "Retail Vault"})
        detail = client.get(f"/api/v1/commercial/orders/{order_id}", headers=headers)
        inventory = client.get("/api/v1/inventory/retail/packages", headers=headers)
    finally: app.dependency_overrides.clear()
    assert vendor.status_code == 201 and order.status_code == 201 and confirmed.status_code == 200
    assert receipt.status_code == 201
    assert receipt.json()["quantity_delta"] == 25
    assert detail.json()["order"]["status"] == "fulfilled"
    assert detail.json()["lines"][0]["fulfilled_quantity"] == 25
    received = next(row for row in inventory.json()["items"] if row["package_id"] == "1A-PO-1")
    assert received["available"] == 25


def test_api_request_ids_stable_errors_and_database_readiness():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-Request-ID": "browser-test-123"}
    try:
        ready = client.get("/health/ready", headers=headers)
        missing = client.get("/api/v1/product-master/not-real", headers=headers)
        invalid = client.post("/api/v1/product-master", headers={**headers, "X-User-Role": "admin"}, json={"sku": ""})
    finally: app.dependency_overrides.clear()
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.headers["X-Request-ID"] == "browser-test-123"
    assert ready.headers["X-Content-Type-Options"] == "nosniff"
    assert missing.status_code == 404
    assert missing.json()["error"] == {"code": "not_found", "message": "Product was not found in this organization.", "request_id": "browser-test-123"}
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_retail_insights_use_durable_sales_inventory_and_receipt_ledgers():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "analyst@example.com", "X-User-Role": "buyer"}
    now = datetime.now(timezone.utc)
    try:
        imported = client.post("/api/v1/inventory/retail/sales/import", headers=headers, json={"source_system": "dutchie", "import_batch_id": "insights-1", "lines": [{"source_record_id": "before-1", "sold_at": (now - timedelta(days=3)).isoformat(), "quantity": 2, "product_id": "product-1", "sku": "BD-BULK", "product_name": "Blue Dream Bulk Flower", "net_sales": 20}, {"source_record_id": "after-1", "sold_at": (now + timedelta(days=2)).isoformat(), "quantity": 5, "product_id": "product-1", "sku": "BD-BULK", "product_name": "Blue Dream Bulk Flower", "net_sales": 60}]})
        trends = client.get("/api/v1/retail-insights/trends?days=30", headers=headers)
        slow = client.get("/api/v1/retail-insights/slow-movers?days=30&threshold_doh=60", headers=headers)
        deliveries = client.get("/api/v1/retail-insights/deliveries", headers=headers)
        impact = client.get(f"/api/v1/retail-insights/deliveries/{deliveries.json()[0]['transaction_id']}/impact?window_days=14", headers=headers)
    finally: app.dependency_overrides.clear()
    assert imported.status_code == 201
    assert trends.status_code == 200
    assert trends.json()["summary"]["net_sales"] == 20
    assert trends.json()["products"][0]["product_id"] == "product-1"
    assert slow.status_code == 200
    assert slow.json()["items"][0]["days_on_hand"] > 60
    assert deliveries.json()[0]["product_id"] == "product-1"
    assert impact.status_code == 200
    assert impact.json()["before"]["net_sales"] == 20
    assert impact.json()["after"]["net_sales"] == 60
    assert impact.json()["lift"]["net_sales"] == 40


def test_purchasing_policy_drives_case_pack_recommendation_and_inbound_po():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "buyer@example.com", "X-User-Role": "buyer"}
    now = datetime.now(timezone.utc)
    try:
        vendor = client.post("/api/v1/commercial/partners", headers={**headers, "X-User-Role": "admin"}, json={"name": "Planning Vendor", "partner_type": "vendor"})
        imported = client.post("/api/v1/inventory/retail/sales/import", headers=headers, json={"source_system": "dutchie", "import_batch_id": "planning", "lines": [{"source_record_id": "planning-sale", "sold_at": (now - timedelta(days=1)).isoformat(), "quantity": 30, "product_id": "product-1", "sku": "BD-BULK", "product_name": "Blue Dream Bulk Flower", "net_sales": 300}]})
        policy = client.post("/api/v1/purchasing/policies/product-1", headers=headers, json={"preferred_vendor_id": vendor.json()["id"], "target_doh": 180, "safety_stock": 0, "reorder_point": 20, "minimum_order_quantity": 24, "case_pack": 12, "velocity_window_days": 30})
        before = client.get("/api/v1/purchasing/workspace", headers=headers)
        recommendation = next(row for row in before.json()["recommendations"] if row["product_id"] == "product-1")
        po = client.post("/api/v1/purchasing/purchase-orders", headers=headers, json={"vendor_id": vendor.json()["id"], "order_number": "PO-PLAN-1", "lines": [{"product_id": "product-1", "quantity": recommendation["suggested_quantity"], "unit": "g", "unit_price": 2}]})
        draft = client.get("/api/v1/purchasing/workspace", headers=headers)
        confirmed = client.post(f"/api/v1/commercial/orders/{po.json()['id']}/actions/confirm", headers=headers, json={})
        after = client.get("/api/v1/purchasing/workspace", headers=headers)
        updated = next(row for row in after.json()["recommendations"] if row["product_id"] == "product-1")
    finally: app.dependency_overrides.clear()
    assert imported.status_code == 201 and policy.status_code == 200
    assert recommendation["suggested_quantity"] == 84
    assert recommendation["preferred_vendor_name"] == "Planning Vendor"
    assert po.status_code == 201 and po.json()["status"] == "draft"
    assert next(row for row in draft.json()["recommendations"] if row["product_id"] == "product-1")["inbound"] == 0
    assert confirmed.status_code == 200
    assert updated["inbound"] == 84
    assert updated["suggested_quantity"] == 0
    assert after.json()["open_purchase_orders"][0]["order_number"] == "PO-PLAN-1"


def test_legal_gate_is_fail_closed_and_records_immutable_acceptance():
    engine = _engine()
    with Session(engine) as session:
        session.add(AppUser(id="legal-user", organization_id="org-1", username="legal", normalized_username="legal", display_name="Legal User", email="legal@example.com", password_hash="$2b$12$placeholder", role="buyer", active=True, created_by="admin", updated_by="admin")); session.commit()
    app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "legal-user", "X-User-Role": "buyer", "User-Agent": "BuyerDashBrowserTest/1.0", "X-Forwarded-For": "203.0.113.10"}
    try:
        current = client.get("/api/v1/legal/current", headers=headers)
        refused = client.post("/api/v1/legal/accept", headers=headers, json={"accepted": False})
        accepted = client.post("/api/v1/legal/accept", headers=headers, json={"accepted": True})
        repeated = client.post("/api/v1/legal/accept", headers=headers, json={"accepted": True})
        after = client.get("/api/v1/legal/current", headers=headers)
    finally: app.dependency_overrides.clear()
    assert current.status_code == 200 and current.json()["accepted"] is False
    assert current.json()["terms"]["version"] == "2026-08-1"
    assert refused.status_code == 422
    assert accepted.status_code == 201
    assert repeated.json()["id"] == accepted.json()["id"]
    assert after.json()["accepted"] is True
    with Session(engine) as session:
        events = list(session.scalars(select(LegalAcceptanceEvent)))
        assert len(events) == 1
        assert events[0].ip_address == "203.0.113.10"
        assert events[0].user_agent == "BuyerDashBrowserTest/1.0"


def test_admin_links_supabase_identity_and_enforces_facility_role_boundaries():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; client = TestClient(app)
    admin = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "admin-user", "X-User-Role": "admin"}
    buyer = {**admin, "X-User-Role": "buyer"}
    try:
        forbidden = client.get("/api/v1/admin/users", headers=buyer)
        linked = client.post("/api/v1/admin/users/link", headers=admin, json={"auth_user_id": "supabase-auth-1", "email": "newbuyer@example.com", "display_name": "New Buyer", "role": "buyer", "facility_ids": ["facility-1"]})
        listed = client.get("/api/v1/admin/users", headers=admin)
        updated = client.post("/api/v1/admin/users/supabase-auth-1", headers=admin, json={"email": "newbuyer@example.com", "display_name": "New Supervisor", "role": "supervisor", "facility_ids": ["facility-1"], "active": True})
        bad_facility = client.post("/api/v1/admin/users/supabase-auth-1", headers=admin, json={"email": "newbuyer@example.com", "display_name": "Bad", "role": "buyer", "facility_ids": ["other-facility"], "active": True})
    finally: app.dependency_overrides.clear()
    assert forbidden.status_code == 403
    assert linked.status_code == 201
    assert linked.json()["facility_ids"] == ["facility-1"]
    assert any(row["id"] == "supabase-auth-1" for row in listed.json())
    assert updated.json()["role"] == "supervisor"
    assert bad_facility.status_code == 422
    with Session(engine) as session:
        user = session.get(AppUser, "supabase-auth-1"); assignment = session.scalar(select(AppUserFacilityRole).where(AppUserFacilityRole.user_id == user.id))
        assert user.password_hash == "supabase-managed"
        assert assignment.role == "supervisor"


def test_integration_credentials_are_encrypted_masked_and_role_scoped():
    engine = _engine(); app.dependency_overrides[get_engine] = lambda: engine; app.dependency_overrides[get_settings] = lambda: Settings(app_env="test", integration_encryption_key="test-only-credential-key")
    client = TestClient(app); buyer = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "integration-user", "X-User-Role": "buyer"}; dev = {**buyer, "X-User-Id": "dev-user", "X-User-Role": "dev"}
    try:
        metrc = client.post("/api/v1/integrations/metrc", headers=buyer, json={"state": "MA", "license_number": "LIC-123", "api_key": "secret-metrc-1234"})
        listing = client.get("/api/v1/integrations", headers=buyer)
        forbidden = client.post("/api/v1/integrations/doobie", headers=buyer, json={"base_url": "https://doobie.example", "api_key": "doobie-secret"})
        doobie = client.post("/api/v1/integrations/doobie", headers=dev, json={"base_url": "https://doobie.example/", "api_key": "doobie-secret-9876"})
        dev_listing = client.get("/api/v1/integrations", headers=dev)
    finally: app.dependency_overrides.clear()
    assert metrc.status_code == 200 and metrc.json()["secret_hint"] == "••••1234"
    assert "api_key" not in json.dumps(listing.json()) and "secret-metrc" not in json.dumps(listing.json())
    assert listing.json()["doobie"] is None
    assert forbidden.status_code == 403
    assert doobie.json()["configuration"]["base_url"] == "https://doobie.example"
    assert dev_listing.json()["doobie"]["secret_hint"] == "••••9876"
    with Session(engine) as session:
        rows = list(session.scalars(select(IntegrationConfiguration)))
        assert len(rows) == 2
        assert all("secret" not in row.encrypted_secret for row in rows)
        assert all(row.encrypted_secret.startswith("gAAAA") for row in rows)
