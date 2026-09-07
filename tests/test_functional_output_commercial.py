from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, CommercialOrder, CommercialOrderLine, OrderLotAllocation
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialInvoice, CommercialInvoiceLine, CommercialShipment
from modules.commercial_finance.service import CommercialFinanceService
from modules.inventory_availability.service import InventoryAvailabilityService


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)

    organization = coman.create_organization("Functional Commercial Output")
    facility = coman.create_facility(organization.id, "Wholesale + Manufacturing", "FO-WHOLESALE")
    product = coman.create_product(
        organization.id,
        sku="FO-GMO-CASE",
        name="GMO Pre-Roll Case",
        item_type="finished_good",
        base_unit="case",
        unit_cost=25,
        retail_price=70,
        actor="acceptance-seed",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="FO-GMO-CASE-LOT-1",
        actor="acceptance-seed",
        opening_quantity=20,
        unit="case",
    )
    customer = commercial.create_trade_partner(
        organization.id,
        name="Functional Output Retailer",
        partner_type="customer",
        actor="sales",
        license_or_registration="MR281234",
        payment_terms="Net 30",
    )
    order = commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number="FO-SO-1001",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{
            "product_id": product.id,
            "description": "GMO Pre-Roll Case",
            "quantity": 10,
            "unit": "case",
            "unit_price": 42.50,
        }],
        actor="sales",
    )
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    return engine, coman, commercial, organization, facility, product, lot, customer, order, line


def test_sales_order_partial_pick_ship_invoice_and_payment_reconcile_exactly():
    (
        engine,
        coman,
        commercial,
        organization,
        facility,
        _product,
        lot,
        _customer,
        order,
        line,
    ) = _setup()

    before = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert before["on_hand"] == 20
    assert before["reserved"] == 0
    assert before["available"] == 20

    confirmed = commercial.confirm_order(
        order.id,
        organization_id=organization.id,
        facility_id=facility.id,
        actor="sales",
    )
    assert confirmed.status == "confirmed"
    committed = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert committed["on_hand"] == 20
    assert committed["wholesale_committed"] == 10
    assert committed["wholesale_reserved"] == 0
    assert committed["reserved"] == 10
    assert committed["available"] == 10

    allocation = commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="warehouse",
    )
    assert allocation.quantity == 10
    assert allocation.fulfilled_quantity == 0
    assert allocation.status == "reserved"
    allocated = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert allocated["wholesale_committed"] == 0
    assert allocated["wholesale_reserved"] == 10
    assert allocated["reserved"] == 10
    assert allocated["available"] == 10

    with pytest.raises(ValueError, match="remaining order-line quantity"):
        commercial.allocate_lot(
            organization_id=organization.id,
            facility_id=facility.id,
            order_line_id=line.id,
            lot_id=lot.id,
            quantity=1,
            actor="warehouse",
        )

    finance = CommercialFinanceService(engine)
    shipment = finance.create_shipment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        shipment_number="FO-SHIP-1001",
        actor="warehouse",
        manifest_reference="FO-MANIFEST-1001",
        carrier="In-house route",
        tracking_reference="ROUTE-1001",
    )
    assert shipment.status == "planned"
    for status in ("picking", "packed", "manifested"):
        shipment = finance.update_shipment_status(
            organization_id=organization.id,
            facility_id=facility.id,
            shipment_id=shipment.id,
            status=status,
        )
        assert shipment.status == status

    first = commercial.post_fulfillment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=4,
        actor="warehouse",
        reference="FO-SHIP-1001-PART-1",
    )
    assert first.transaction_type == "shipment"
    assert first.quantity_delta == -4
    assert first.reference == "FO-SHIP-1001-PART-1"
    assert coman.inventory_balance(organization.id, lot.id) == 16

    partial_order = commercial.list_orders(organization.id, facility.id)[0]
    partial_line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    partial_allocation = commercial.list_allocations(organization.id, facility.id, order_id=order.id)[0]
    assert partial_order.status == "partially_fulfilled"
    assert partial_line.quantity == 10
    assert partial_line.fulfilled_quantity == 4
    assert partial_allocation.quantity == 10
    assert partial_allocation.fulfilled_quantity == 4
    assert partial_allocation.status == "partial"

    partial_inventory = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert partial_inventory["on_hand"] == 16
    assert partial_inventory["wholesale_reserved"] == 6
    assert partial_inventory["wholesale_committed"] == 0
    assert partial_inventory["reserved"] == 6
    assert partial_inventory["available"] == 10

    second = commercial.post_fulfillment(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=6,
        actor="warehouse",
        reference="FO-SHIP-1001-PART-2",
    )
    assert second.transaction_type == "shipment"
    assert second.quantity_delta == -6
    assert coman.inventory_balance(organization.id, lot.id) == 10

    fulfilled_order = commercial.list_orders(organization.id, facility.id)[0]
    fulfilled_line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    fulfilled_allocation = commercial.list_allocations(organization.id, facility.id, order_id=order.id)[0]
    assert fulfilled_order.status == "fulfilled"
    assert fulfilled_line.fulfilled_quantity == 10
    assert fulfilled_allocation.fulfilled_quantity == 10
    assert fulfilled_allocation.status == "fulfilled"

    final_inventory = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert final_inventory["on_hand"] == 10
    assert final_inventory["wholesale_reserved"] == 0
    assert final_inventory["wholesale_committed"] == 0
    assert final_inventory["reserved"] == 0
    assert final_inventory["available"] == 10

    shipped = finance.update_shipment_status(
        organization_id=organization.id,
        facility_id=facility.id,
        shipment_id=shipment.id,
        status="shipped",
    )
    assert shipped.status == "shipped"
    assert shipped.shipped_at is not None
    delivered = finance.update_shipment_status(
        organization_id=organization.id,
        facility_id=facility.id,
        shipment_id=shipment.id,
        status="delivered",
    )
    assert delivered.status == "delivered"
    assert delivered.shipped_at is not None
    assert delivered.delivered_at is not None

    invoice = finance.create_invoice_from_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        invoice_number="FO-INV-1001",
        actor="accounting",
        due_days=30,
        discount_usd=25,
        tax_usd=5,
    )
    assert invoice.status == "draft"
    assert invoice.subtotal_usd == 425
    assert invoice.discount_usd == 25
    assert invoice.tax_usd == 5
    assert invoice.total_usd == 405
    assert invoice.balance_usd == 405

    with Session(engine) as session:
        invoice_line = session.scalar(select(CommercialInvoiceLine).where(CommercialInvoiceLine.invoice_id == invoice.id))
        assert invoice_line is not None
        assert invoice_line.commercial_order_line_id == line.id
        assert invoice_line.quantity == 10
        assert invoice_line.unit_price_usd == 42.50
        assert invoice_line.line_total_usd == 425

    sent = finance.send_invoice(
        organization_id=organization.id,
        facility_id=facility.id,
        invoice_id=invoice.id,
    )
    assert sent.status == "sent"
    assert commercial.list_orders(organization.id, facility.id)[0].payment_status == "sent"

    first_payment = finance.record_payment(
        organization_id=organization.id,
        facility_id=facility.id,
        invoice_id=invoice.id,
        amount_usd=105,
        actor="accounting",
        method="ach",
        reference="FO-PAY-1001-A",
    )
    assert first_payment.amount_usd == 105
    assert first_payment.reference == "FO-PAY-1001-A"
    with Session(engine) as session:
        partial_invoice = session.get(CommercialInvoice, invoice.id)
        assert partial_invoice is not None
        assert partial_invoice.status == "partial"
        assert partial_invoice.balance_usd == 300
    assert commercial.list_orders(organization.id, facility.id)[0].payment_status == "partial"

    with pytest.raises(ValueError, match="exceeds the remaining invoice balance"):
        finance.record_payment(
            organization_id=organization.id,
            facility_id=facility.id,
            invoice_id=invoice.id,
            amount_usd=300.01,
            actor="accounting",
        )

    final_payment = finance.record_payment(
        organization_id=organization.id,
        facility_id=facility.id,
        invoice_id=invoice.id,
        amount_usd=300,
        actor="accounting",
        method="ach",
        reference="FO-PAY-1001-B",
    )
    assert final_payment.amount_usd == 300
    with Session(engine) as session:
        paid_invoice = session.get(CommercialInvoice, invoice.id)
        stored_order = session.get(CommercialOrder, order.id)
        stored_line = session.get(CommercialOrderLine, line.id)
        stored_allocation = session.scalar(select(OrderLotAllocation).where(OrderLotAllocation.commercial_order_id == order.id))
        stored_shipment = session.get(CommercialShipment, shipment.id)
        assert paid_invoice is not None and stored_order is not None and stored_line is not None
        assert stored_allocation is not None and stored_shipment is not None
        assert paid_invoice.status == "paid"
        assert paid_invoice.balance_usd == 0
        assert stored_order.status == "fulfilled"
        assert stored_order.payment_status == "paid"
        assert stored_line.fulfilled_quantity == 10
        assert stored_allocation.status == "fulfilled"
        assert stored_shipment.status == "delivered"
        assert stored_shipment.manifest_reference == "FO-MANIFEST-1001"
        assert stored_shipment.carrier == "In-house route"
        assert stored_shipment.tracking_reference == "ROUTE-1001"

    order_finance = finance.order_finance(organization.id, facility.id, order.id)
    assert [row.id for row in order_finance["invoices"]] == [invoice.id]
    assert [row.id for row in order_finance["shipments"]] == [shipment.id]
    assert finance.ar_summary(organization.id, facility.id)["total_ar"] == 0
