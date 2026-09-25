from __future__ import annotations

from datetime import date, datetime, timedelta
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, CommercialOrder, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commerce_storefronts.intelligence import StorefrontWholesaleIntelligenceService
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialInvoice
from modules.commercial_finance.service import CommercialFinanceService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _base():
    engine = _engine()
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)
    organization = coman.create_organization("Wholesale Continuity QA")
    facility = coman.create_facility(organization.id, "MA Wholesale", "MA-WHOLESALE")
    return engine, coman, commercial, organization, facility


def test_regulated_sales_inventory_rechecks_release_and_requires_manifested_shipment():
    engine, coman, commercial, organization, facility = _base()
    product = coman.create_product(
        organization.id,
        sku="REG-CASE",
        name="Regulated Case",
        item_type="finished_good",
        base_unit="case",
        unit_cost=20,
        retail_price=60,
        actor="seed",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="REG-LOT-1",
        actor="seed",
        opening_quantity=10,
        unit="case",
    )
    with Session(engine) as session, session.begin():
        stored = session.get(InventoryLot, lot.id)
        stored.compliance_package_id = "1A406030000MA00001"
        stored.status = "available"

    customer = commercial.create_trade_partner(
        organization.id,
        name="Licensed Retailer",
        partner_type="customer",
        actor="seed",
        license_or_registration="MR281234",
    )
    order = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number="SO-REG-1",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{"product_id": product.id, "quantity": 2, "unit": "case", "unit_price": 50}],
        actor="sales",
    )
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=2,
        actor="warehouse",
    )

    with pytest.raises(ValueError, match="manifested shipment"):
        commercial.post_fulfillment(
            organization_id=organization.id,
            facility_id=facility.id,
            order_line_id=line.id,
            lot_id=lot.id,
            quantity=1,
            actor="warehouse",
        )

    finance = CommercialFinanceService(engine)
    no_manifest = finance.create_shipment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        shipment_number="SHP-REG-NO-MANIFEST",
        actor="warehouse",
    )
    with pytest.raises(ValueError, match="Manifest reference"):
        finance.update_shipment_status(
            organization_id=organization.id,
            facility_id=facility.id,
            shipment_id=no_manifest.id,
            status="manifested",
        )
    finance.update_shipment_status(
        organization_id=organization.id,
        facility_id=facility.id,
        shipment_id=no_manifest.id,
        status="packed",
    )
    updated_manifest = finance.update_shipment_status(
        organization_id=organization.id,
        facility_id=facility.id,
        shipment_id=no_manifest.id,
        status="manifested",
        manifest_reference="MA-MANIFEST-LATE-1001",
    )
    assert updated_manifest.manifest_reference == "MA-MANIFEST-LATE-1001"

    shipment = finance.create_shipment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        shipment_number="SHP-REG-1",
        actor="warehouse",
        manifest_reference="MA-MANIFEST-1001",
    )
    finance.update_shipment_status(
        organization_id=organization.id,
        facility_id=facility.id,
        shipment_id=shipment.id,
        status="manifested",
    )

    with Session(engine) as session, session.begin():
        session.get(InventoryLot, lot.id).status = "hold"

    with pytest.raises(ValueError, match="QA or inventory hold"):
        commercial.post_fulfillment(
            organization_id=organization.id,
            facility_id=facility.id,
            order_line_id=line.id,
            lot_id=lot.id,
            quantity=1,
            actor="warehouse",
        )

    with Session(engine) as session, session.begin():
        session.get(InventoryLot, lot.id).status = "available"

    shipped = commercial.post_fulfillment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=1,
        actor="warehouse",
        reference="SHP-REG-1",
    )
    assert shipped.transaction_type == "shipment"
    assert shipped.quantity_delta == -1


def test_wholesale_intelligence_surfaces_full_order_to_cash_exception_set():
    engine, coman, commercial, organization, facility = _base()
    today = date.today()

    low_margin_product = coman.create_product(
        organization.id,
        sku="MARGIN-CASE",
        name="Margin Case",
        item_type="finished_good",
        base_unit="case",
        unit_cost=90,
        retail_price=120,
        actor="seed",
    )
    low_margin_lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=low_margin_product.id,
        lot_code="MARGIN-LOT",
        actor="seed",
        opening_quantity=20,
        unit="case",
    )
    with Session(engine) as session, session.begin():
        stored = session.get(InventoryLot, low_margin_lot.id)
        stored.compliance_package_id = "1A406030000MA00002"
        stored.status = "available"
        stored.notes = json.dumps({"lab_testing_state": "Passed", "coa_reference": "COA-MARGIN"})

    ar_product = coman.create_product(
        organization.id,
        sku="AR-SERVICE",
        name="Prior Wholesale Item",
        item_type="finished_good",
        base_unit="case",
        unit_cost=20,
        retail_price=100,
        actor="seed",
    )
    fulfilled_product = coman.create_product(
        organization.id,
        sku="FULFILLED-CASE",
        name="Fulfilled Case",
        item_type="finished_good",
        base_unit="case",
        unit_cost=20,
        retail_price=100,
        actor="seed",
    )
    fulfilled_lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=fulfilled_product.id,
        lot_code="FULFILLED-LOT",
        actor="seed",
        opening_quantity=5,
        unit="case",
    )

    customer = commercial.create_trade_partner(
        organization.id,
        name="Continuity Retailer",
        partner_type="customer",
        actor="seed",
        license_or_registration="MR-CONTINUITY",
        payment_terms="Net 30",
    )

    prior = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number="SO-AR-OLD",
        order_type="sales",
        order_date=today - timedelta(days=60),
        due_date=today - timedelta(days=45),
        lines=[{"product_id": ar_product.id, "quantity": 1, "unit": "case", "unit_price": 100}],
        actor="sales",
    )
    finance = CommercialFinanceService(engine)
    with pytest.raises(ValueError, match="Complete sales-order fulfillment"):
        finance.create_invoice_from_order(
            organization_id=organization.id,
            facility_id=facility.id,
            order_id=prior.id,
            invoice_number="INV-AR-PREMATURE",
            actor="accounting",
            require_fulfilled=True,
        )
    old_invoice = finance.create_invoice_from_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=prior.id,
        invoice_number="INV-AR-OLD",
        actor="accounting",
        due_days=0,
    )
    finance.send_invoice(
        organization_id=organization.id,
        facility_id=facility.id,
        invoice_id=old_invoice.id,
    )
    with Session(engine) as session, session.begin():
        invoice = session.get(CommercialInvoice, old_invoice.id)
        invoice.due_date = today - timedelta(days=30)

    storefront = WholesaleCommerceStorefrontService(engine)
    storefront.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Continuity Wholesale",
        subdomain="continuity-wholesale",
        published=True,
    )
    storefront.set_products(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        products=[{"product_id": low_margin_product.id, "price_usd": 100, "minimum_quantity": 1, "case_quantity": 1}],
    )

    pending = storefront.submit_order_request(
        slug="continuity-wholesale",
        buyer_company=customer.name,
        buyer_license=customer.license_or_registration,
        buyer_contact="Buyer",
        buyer_email="buyer@example.test",
        lines=[{"product_id": low_margin_product.id, "quantity": 1}],
    )
    assert pending.status == "submitted"

    operational_request = storefront.submit_order_request(
        slug="continuity-wholesale",
        buyer_company=customer.name,
        buyer_license=customer.license_or_registration,
        buyer_contact="Buyer",
        buyer_email="buyer@example.test",
        requested_delivery_date=today - timedelta(days=2),
        lines=[{"product_id": low_margin_product.id, "quantity": 4}],
    )
    approved = storefront.approve_order_request(
        organization_id=organization.id,
        facility_id=facility.id,
        request_id=operational_request.id,
        actor="sales-manager",
    )
    operational_order_id = approved["order_id"]
    line = commercial.list_order_lines(organization.id, order_id=operational_order_id)[0]
    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=low_margin_lot.id,
        quantity=4,
        actor="warehouse",
    )
    with Session(engine) as session, session.begin():
        stored_order = session.get(CommercialOrder, operational_order_id)
        stored_order.due_at = datetime.combine(today - timedelta(days=2), datetime.min.time())
        session.get(InventoryLot, low_margin_lot.id).status = "hold"

    fulfilled = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number="SO-FULFILLED-NO-INVOICE",
        order_type="sales",
        order_date=today,
        due_date=today,
        lines=[{"product_id": fulfilled_product.id, "quantity": 2, "unit": "case", "unit_price": 100}],
        actor="sales",
    )
    commercial.confirm_order(fulfilled.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    fulfilled_line = commercial.list_order_lines(organization.id, order_id=fulfilled.id)[0]
    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=fulfilled_line.id,
        lot_id=fulfilled_lot.id,
        quantity=2,
        actor="warehouse",
    )
    commercial.post_fulfillment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=fulfilled_line.id,
        lot_id=fulfilled_lot.id,
        quantity=2,
        actor="warehouse",
    )

    snapshot = StorefrontWholesaleIntelligenceService(engine).snapshot(organization.id, facility.id)
    kinds = {row["kind"] for row in snapshot["order_to_cash_exceptions"]}

    assert {
        "customer_ar_pending_order",
        "low_margin_order",
        "qa_hold",
        "waiting_manifest",
        "late_fulfillment",
        "invoice_ar_handoff",
    }.issubset(kinds)
    summary = snapshot["summary"]
    assert summary["customer_ar_pending_orders"] >= 1
    assert summary["low_margin_orders"] >= 1
    assert summary["qa_hold_orders"] >= 1
    assert summary["orders_waiting_manifest"] >= 1
    assert summary["late_fulfillment_orders"] >= 1
    assert summary["invoice_ar_handoff_orders"] >= 1

    manifest = next(row for row in snapshot["order_to_cash_exceptions"] if row["kind"] == "waiting_manifest")
    assert manifest["order_id"] == operational_order_id
    assert manifest["manifest_state"] == "not_started"
    qa = next(row for row in snapshot["order_to_cash_exceptions"] if row["kind"] == "qa_hold")
    assert qa["lots"][0]["status"] == "hold"

    flow = {row["order_id"]: row for row in snapshot["order_to_cash"]["orders"]}
    assert flow[operational_order_id]["stage"] == "shipment_setup_required"
    assert flow[operational_order_id]["estimated_gross_margin_pct"] == 10.0
    assert flow[fulfilled.id]["stage"] == "invoice_required"
    assert snapshot["order_to_cash"]["stage_counts"]["invoice_required"] >= 1
