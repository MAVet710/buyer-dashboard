from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization, Product
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.service import CommercialFinanceService
from services.quickbooks_sync import QuickBooksSyncService
from services.wholesale_accounting import WholesaleAccountingService


ROOT = Path(__file__).resolve().parents[1]
KEY = "test"


def _seed_accounting():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Wholesale Accounting", slug="wholesale-accounting")
        session.add(org); session.flush()
        facility = Facility(organization_id=org.id, name="Wholesale", code="WHOLE", retail_enabled=True, production_enabled=True, commercial_enabled=True)
        session.add(facility); session.flush()
        product = Product(organization_id=org.id, sku="FLOWER-1", name="Wholesale Flower", item_type="cannabis", base_unit="unit", unit_cost=10, retail_price=20)
        session.add(product); session.flush()
        org_id, facility_id, product_id = org.id, facility.id, product.id
    repo = CommercialRepository(engine)
    customer = repo.create_trade_partner(org_id, name="Retail Customer", partner_type="customer", actor="admin", payment_terms="Net 30")
    order = repo.create_order(
        organization_id=org_id,
        facility_id=facility_id,
        partner_id=customer.id,
        order_number="SO-100",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{"product_id": product_id, "description": "Wholesale Flower", "quantity": 10, "unit": "unit", "unit_price": 10}],
        actor="admin",
    )
    finance = CommercialFinanceService(engine)
    invoice = finance.create_invoice_from_order(
        organization_id=org_id,
        facility_id=facility_id,
        order_id=order.id,
        invoice_number="INV-100",
        actor="admin",
        due_days=30,
    )
    finance.send_invoice(organization_id=org_id, facility_id=facility_id, invoice_id=invoice.id)
    finance.record_payment(
        organization_id=org_id,
        facility_id=facility_id,
        invoice_id=invoice.id,
        amount_usd=25,
        actor="admin",
        method="ach",
        reference="PAY-25",
    )
    sync = QuickBooksSyncService(engine, KEY)
    with Session(engine) as session, session.begin():
        sync._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="customer", internal_id=customer.id, external_id="QBO-CUST-1", actor="admin")
        sync._upsert_link(session, organization_id=org_id, facility_id=facility_id, entity_type="invoice", internal_id=invoice.id, external_id="QBO-INV-1", actor="admin")
    sync.map_product_item(organization_id=org_id, facility_id=facility_id, product_id=product_id, qbo_item_id="QBO-ITEM-1", actor="admin")
    return engine, org_id, facility_id


def test_wholesale_accounting_pools_ar_invoice_payment_order_and_qbo_linkage():
    engine, org_id, facility_id = _seed_accounting()
    snapshot = WholesaleAccountingService(engine, KEY).snapshot(org_id, facility_id)
    assert snapshot["read_only"] is True
    assert snapshot["summary"]["total_ar"] == 75.0
    assert snapshot["summary"]["open_invoice_count"] == 1
    assert snapshot["summary"]["payments_30d"] == 25.0
    assert snapshot["summary"]["open_sales_order_value"] == 100.0
    assert snapshot["invoices"][0]["invoice_number"] == "INV-100"
    assert snapshot["invoices"][0]["balance_usd"] == 75.0
    assert snapshot["invoices"][0]["qbo_id"] == "QBO-INV-1"
    assert snapshot["recent_payments"][0]["reference"] == "PAY-25"
    assert snapshot["sales_orders"][0]["payment_status"] == "partial"
    assert snapshot["quickbooks"]["linked_entities"]["customer"] == 1
    assert snapshot["quickbooks"]["linked_entities"]["invoice"] == 1
    assert snapshot["quickbooks"]["linked_entities"]["item"] == 1
    assert "does not claim a fresh remote-provider readback" in snapshot["quickbooks"]["message"]


def test_wholesale_accounting_stays_available_when_quickbooks_runtime_is_not_configured():
    engine, org_id, facility_id = _seed_accounting()
    snapshot = WholesaleAccountingService(engine, "").snapshot(org_id, facility_id)
    assert snapshot["summary"]["total_ar"] == 75.0
    assert snapshot["summary"]["qbo_connected"] is False
    assert snapshot["quickbooks"]["purchasing_reconciliation"]["read_only"] is True
    assert "Local wholesale accounting remains available" in snapshot["quickbooks"]["purchasing_reconciliation"]["message"]


def test_wholesale_accounting_routes_and_frontend_are_first_class_but_sync_stays_admin_governed():
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    accounting_router = (ROOT / "backend/app/routers/wholesale_accounting.py").read_text(encoding="utf-8")
    qbo_router = (ROOT / "backend/app/routers/quickbooks_purchasing.py").read_text(encoding="utf-8")
    wholesale = (ROOT / "frontend/src/pages/WholesaleOpsPage.tsx").read_text(encoding="utf-8")
    panel = (ROOT / "frontend/src/pages/WholesaleAccountingPanel.tsx").read_text(encoding="utf-8")

    assert "wholesale_accounting_router" in main and "quickbooks_purchasing_router" in main
    assert 'prefix="/commercial/accounting"' in accounting_router
    assert "dependencies=[Depends(get_commercial_context)]" in accounting_router
    assert 'ADMIN_ROLES = {"dev", "admin"}' in qbo_router
    assert '_require_admin(context)' in qbo_router
    assert '"accounting","Accounting"' in wholesale
    assert "WholesaleAccountingPanel" in wholesale
    assert 'title="Accounting"' in wholesale
    assert '"/api/v1/commercial/accounting"' in panel
    for label in ("Accounts receivable", "Overdue A/R", "Wholesale invoices", "Recorded payments", "Accounting synchronization health"):
        assert label in panel