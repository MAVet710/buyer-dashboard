from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import services.quickbooks_purchasing as qbo_purchasing
from modules.coman.models import Base, Facility, Organization, Product
from modules.commercial.repository import CommercialRepository
from modules.integrations.accounting_links import AccountingSyncLink
from services.quickbooks_purchasing import QuickBooksPurchasingSyncService
from services.quickbooks_sync import QuickBooksSyncError


ENCRYPTION_KEY = "test"


def _seed():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="QBO Purchasing", slug="qbo-purchasing")
        session.add(organization); session.flush()
        facility = Facility(organization_id=organization.id, name="QBO Facility", code="QBO-1", retail_enabled=True, production_enabled=True, commercial_enabled=True)
        session.add(facility); session.flush()
        product = Product(organization_id=organization.id, sku="PKG-100", name="Packaging Jar", item_type="packaging", base_unit="unit", unit_cost=1.25, retail_price=0)
        session.add(product); session.flush()
        organization_id, facility_id, product_id = organization.id, facility.id, product.id
    repo = CommercialRepository(engine)
    vendor = repo.create_trade_partner(organization_id, name="Supply Vendor", partner_type="vendor", actor="buyer-1", contact_email="orders@example.test", payment_terms="Net 30")
    order = repo.create_order(
        organization_id=organization_id, facility_id=facility_id, partner_id=vendor.id, order_number="PO-1001", order_type="purchase",
        order_date=date(2026, 8, 30), due_date=date(2026, 9, 6),
        lines=[{"product_id": product_id, "description": "Packaging Jar", "quantity": 100, "unit": "unit", "unit_price": 1.25}],
        actor="buyer-1", external_reference="Vendor quote 88", notes="Human-approved purchasing order",
    )
    return engine, repo, organization_id, facility_id, product_id, vendor.id, order.id


def _offline_connection(service):
    service._connection = lambda organization_id, facility_id, actor: ("token", {"realm_id": "realm-1", "environment": "sandbox", "api_base_url": ""})  # type: ignore[method-assign]


def test_vendor_sync_is_idempotent_and_uses_existing_accounting_link_ledger(monkeypatch):
    engine, _repo, organization_id, facility_id, _product_id, vendor_id, _order_id = _seed()
    service = QuickBooksPurchasingSyncService(engine, ENCRYPTION_KEY); _offline_connection(service); calls = []
    def fake_request(**kwargs):
        calls.append(kwargs); assert kwargs["entity"] == "vendor"; assert kwargs["payload"]["DisplayName"] == "Supply Vendor"
        return {"Vendor": {"Id": "VENDOR-1", "SyncToken": "0"}}
    monkeypatch.setattr(qbo_purchasing, "quickbooks_api_request", fake_request)
    first = service.sync_vendor(organization_id=organization_id, facility_id=facility_id, partner_id=vendor_id, actor="admin-1")
    second = service.sync_vendor(organization_id=organization_id, facility_id=facility_id, partner_id=vendor_id, actor="admin-1")
    assert first == {"ok": True, "skipped": False, "local_id": vendor_id, "qbo_id": "VENDOR-1", "entity": "vendor"}
    assert second["skipped"] is True and len(calls) == 1
    with Session(engine) as session:
        link = session.scalar(select(AccountingSyncLink).where(AccountingSyncLink.entity_type == "vendor"))
        assert link is not None and link.external_id == "VENDOR-1"
        assert session.scalar(select(func.count()).select_from(AccountingSyncLink).where(AccountingSyncLink.entity_type == "vendor")) == 1


def test_purchase_order_sync_blocks_until_human_confirmation_vendor_and_item_mapping(monkeypatch):
    engine, repo, organization_id, facility_id, product_id, vendor_id, order_id = _seed()
    service = QuickBooksPurchasingSyncService(engine, ENCRYPTION_KEY); _offline_connection(service)
    monkeypatch.setattr(qbo_purchasing, "quickbooks_api_request", lambda **_kwargs: pytest.fail("provider must not be called while prerequisites are incomplete"))
    with pytest.raises(QuickBooksSyncError, match="Confirm the purchase order"):
        service.sync_purchase_order(organization_id=organization_id, facility_id=facility_id, order_id=order_id, actor="admin-1")
    repo.confirm_order(order_id, organization_id=organization_id, facility_id=facility_id, actor="buyer-1")
    with pytest.raises(QuickBooksSyncError, match="Synchronize the purchase-order vendor"):
        service.sync_purchase_order(organization_id=organization_id, facility_id=facility_id, order_id=order_id, actor="admin-1")
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=organization_id, facility_id=facility_id, entity_type="vendor", internal_id=vendor_id, external_id="VENDOR-1", actor="admin-1")
    with pytest.raises(QuickBooksSyncError, match="Item mapping is required"):
        service.sync_purchase_order(organization_id=organization_id, facility_id=facility_id, order_id=order_id, actor="admin-1")
    service.map_product_item(organization_id=organization_id, facility_id=facility_id, product_id=product_id, qbo_item_id="ITEM-1", actor="admin-1")


def test_confirmed_purchase_order_posts_deterministic_item_lines_and_skips_unchanged_replay(monkeypatch):
    engine, repo, organization_id, facility_id, product_id, vendor_id, order_id = _seed()
    repo.confirm_order(order_id, organization_id=organization_id, facility_id=facility_id, actor="buyer-1")
    service = QuickBooksPurchasingSyncService(engine, ENCRYPTION_KEY); _offline_connection(service)
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=organization_id, facility_id=facility_id, entity_type="vendor", internal_id=vendor_id, external_id="VENDOR-1", actor="admin-1")
    service.map_product_item(organization_id=organization_id, facility_id=facility_id, product_id=product_id, qbo_item_id="ITEM-1", actor="admin-1")
    calls = []
    def fake_request(**kwargs):
        calls.append(kwargs); assert kwargs["entity"] == "purchaseorder"; payload = kwargs["payload"]
        assert payload["VendorRef"] == {"value": "VENDOR-1"}; assert payload["DocNumber"] == "PO-1001"; assert payload["TxnDate"] == "2026-08-30"
        line = payload["Line"][0]; assert line["Amount"] == 125.0; assert line["DetailType"] == "ItemBasedExpenseLineDetail"
        assert line["ItemBasedExpenseLineDetail"] == {"ItemRef": {"value": "ITEM-1"}, "Qty": 100.0, "UnitPrice": 1.25}
        return {"PurchaseOrder": {"Id": "PO-QBO-1", "SyncToken": "0"}}
    monkeypatch.setattr(qbo_purchasing, "quickbooks_api_request", fake_request)
    first = service.sync_purchase_order(organization_id=organization_id, facility_id=facility_id, order_id=order_id, actor="admin-1")
    second = service.sync_purchase_order(organization_id=organization_id, facility_id=facility_id, order_id=order_id, actor="admin-1")
    assert first["skipped"] is False and first["qbo_id"] == "PO-QBO-1" and second["skipped"] is True and len(calls) == 1


def test_reconciliation_is_read_only_and_reports_local_mapping_or_change_state(monkeypatch):
    engine, repo, organization_id, facility_id, product_id, vendor_id, order_id = _seed()
    repo.confirm_order(order_id, organization_id=organization_id, facility_id=facility_id, actor="buyer-1")
    service = QuickBooksPurchasingSyncService(engine, ENCRYPTION_KEY)
    monkeypatch.setattr(qbo_purchasing, "quickbooks_api_request", lambda **_kwargs: pytest.fail("read-only reconciliation must never call QuickBooks"))
    initial = service.reconciliation_snapshot(organization_id, facility_id)
    assert initial["read_only"] is True and initial["vendors"][0]["status"] == "never_synced" and initial["purchase_orders"][0]["sync_status"] == "blocked_vendor_mapping"
    assert "does not claim remote provider verification" in initial["message"]
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=organization_id, facility_id=facility_id, entity_type="vendor", internal_id=vendor_id, external_id="VENDOR-1", payload_hash="stale-vendor-hash", actor="admin-1")
    mapped_vendor = service.reconciliation_snapshot(organization_id, facility_id)
    assert mapped_vendor["vendors"][0]["status"] == "local_changes_pending" and mapped_vendor["purchase_orders"][0]["sync_status"] == "blocked_item_mapping"
    service.map_product_item(organization_id=organization_id, facility_id=facility_id, product_id=product_id, qbo_item_id="ITEM-1", actor="admin-1")
    assert service.reconciliation_snapshot(organization_id, facility_id)["purchase_orders"][0]["sync_status"] == "never_synced"