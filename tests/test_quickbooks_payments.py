from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import services.quickbooks_payments as qbo_payments
from modules.coman.models import Base, Facility, Organization, Product
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialPayment
from modules.commercial_finance.service import CommercialFinanceService
from modules.integrations.accounting_links import AccountingSyncLink
from services.quickbooks_payments import QuickBooksPaymentSyncService
from services.quickbooks_sync import QuickBooksSyncError

KEY = "test"


def _seed():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="QBO Payments", slug="qbo-payments")
        session.add(org); session.flush()
        facility = Facility(organization_id=org.id, name="Wholesale", code="WHOLE-PAY", retail_enabled=True, production_enabled=True, commercial_enabled=True)
        session.add(facility); session.flush()
        product = Product(organization_id=org.id, sku="FLOWER-PAY", name="Wholesale Flower", item_type="cannabis", base_unit="unit", unit_cost=10, retail_price=20)
        session.add(product); session.flush()
        org_id, facility_id, product_id = org.id, facility.id, product.id
    repo = CommercialRepository(engine)
    customer = repo.create_trade_partner(org_id, name="Retail Customer", partner_type="customer", actor="admin", payment_terms="Net 30")
    order = repo.create_order(organization_id=org_id, facility_id=facility_id, partner_id=customer.id, order_number="SO-PAY-100", order_type="sales", order_date=date(2026, 9, 1), due_date=date(2026, 10, 1), lines=[{"product_id": product_id, "description": "Wholesale Flower", "quantity": 10, "unit": "unit", "unit_price": 10}], actor="admin")
    finance = CommercialFinanceService(engine)
    invoice = finance.create_invoice_from_order(organization_id=org_id, facility_id=facility_id, order_id=order.id, invoice_number="INV-PAY-100", actor="admin", due_days=30)
    finance.send_invoice(organization_id=org_id, facility_id=facility_id, invoice_id=invoice.id)
    payment = finance.record_payment(organization_id=org_id, facility_id=facility_id, invoice_id=invoice.id, amount_usd=25, actor="ar-user", payment_date=date(2026, 9, 5), method="ach", reference="ACH-25", notes="Customer ACH received")
    return engine, org_id, facility_id, customer.id, invoice.id, payment.id


def _offline(service):
    service._connection = lambda organization_id, facility_id, actor: ("token", {"realm_id": "realm-1", "environment": "sandbox", "api_base_url": ""})  # type: ignore[method-assign]


def test_payment_sync_fails_closed_until_invoice_and_customer_are_mapped(monkeypatch):
    engine, org_id, facility_id, customer_id, invoice_id, payment_id = _seed()
    service = QuickBooksPaymentSyncService(engine, KEY); _offline(service)
    monkeypatch.setattr(qbo_payments, "quickbooks_api_request", lambda **_kwargs: pytest.fail("provider must not be called before mappings exist"))
    with pytest.raises(QuickBooksSyncError, match="Synchronize the invoice"):
        service.sync_payment(organization_id=org_id, facility_id=facility_id, payment_id=payment_id, actor="admin")
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="invoice", internal_id=invoice_id, external_id="QBO-INV-1", actor="admin")
    with pytest.raises(QuickBooksSyncError, match="invoice customer"):
        service.sync_payment(organization_id=org_id, facility_id=facility_id, payment_id=payment_id, actor="admin")
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="customer", internal_id=customer_id, external_id="QBO-CUST-1", actor="admin")


def test_payment_sync_posts_exact_invoice_link_and_is_idempotent(monkeypatch):
    engine, org_id, facility_id, customer_id, invoice_id, payment_id = _seed()
    service = QuickBooksPaymentSyncService(engine, KEY); _offline(service)
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="invoice", internal_id=invoice_id, external_id="QBO-INV-1", actor="admin")
        service._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="customer", internal_id=customer_id, external_id="QBO-CUST-1", actor="admin")
    calls = []
    def fake_request(**kwargs):
        calls.append(kwargs)
        assert kwargs["entity"] == "payment"
        payload = kwargs["payload"]
        assert payload["CustomerRef"] == {"value": "QBO-CUST-1"}
        assert payload["TxnDate"] == "2026-09-05"
        assert payload["PaymentType"] == "Other"
        assert payload["PaymentRefNum"] == "ACH-25"
        assert payload["PrivateNote"] == "Customer ACH received"
        assert payload["Line"] == [{"Amount": 25.0, "LinkedTxn": [{"TxnId": "QBO-INV-1", "TxnType": "Invoice"}]}]
        assert "TotalAmt" not in payload
        return {"Payment": {"Id": "QBO-PAY-1", "SyncToken": "0"}}
    monkeypatch.setattr(qbo_payments, "quickbooks_api_request", fake_request)
    first = service.sync_payment(organization_id=org_id, facility_id=facility_id, payment_id=payment_id, actor="admin")
    second = service.sync_payment(organization_id=org_id, facility_id=facility_id, payment_id=payment_id, actor="admin")
    assert first["skipped"] is False and first["qbo_id"] == "QBO-PAY-1" and first["qbo_invoice_id"] == "QBO-INV-1"
    assert second["skipped"] is True and len(calls) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AccountingSyncLink).where(AccountingSyncLink.entity_type == "payment")) == 1


def test_synced_payment_local_drift_never_mutates_remote_automatically(monkeypatch):
    engine, org_id, facility_id, customer_id, invoice_id, payment_id = _seed()
    service = QuickBooksPaymentSyncService(engine, KEY); _offline(service)
    with Session(engine) as session, session.begin():
        service._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="invoice", internal_id=invoice_id, external_id="QBO-INV-1", actor="admin")
        service._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="customer", internal_id=customer_id, external_id="QBO-CUST-1", actor="admin")
    monkeypatch.setattr(qbo_payments, "quickbooks_api_request", lambda **_kwargs: {"Payment": {"Id": "QBO-PAY-1", "SyncToken": "0"}})
    service.sync_payment(organization_id=org_id, facility_id=facility_id, payment_id=payment_id, actor="admin")
    with Session(engine) as session, session.begin():
        row = session.get(CommercialPayment, payment_id); assert row is not None
        row.reference = "CHANGED-AFTER-SYNC"
    monkeypatch.setattr(qbo_payments, "quickbooks_api_request", lambda **_kwargs: pytest.fail("provider update must remain blocked"))
    with pytest.raises(QuickBooksSyncError, match="Automatic Payment mutation is blocked"):
        service.sync_payment(organization_id=org_id, facility_id=facility_id, payment_id=payment_id, actor="admin")


def test_payment_sync_route_stays_admin_governed():
    source = open("backend/app/routers/quickbooks_purchasing.py", encoding="utf-8").read()
    assert '@router.post("/payments/{payment_id}/sync")' in source
    assert "_require_admin(context)" in source
    assert ".sync_payment(" in source
