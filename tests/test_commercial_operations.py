from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine

from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.commercial.analytics import commercial_dashboard_metrics
from modules.commercial.repository import CommercialRepository


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)
    org = coman.create_organization("Commercial QA")
    facility = coman.create_facility(org.id, "Main", "MAIN")
    product = coman.create_product(
        org.id,
        sku="FG-35",
        name="Flower 3.5g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=8,
        actor="dev",
    )
    return coman, commercial, org, facility, product


def _order(commercial, org, facility, product, partner, *, order_type, number, quantity=10):
    return commercial.create_order(
        organization_id=org.id,
        facility_id=facility.id,
        partner_id=partner.id,
        order_number=number,
        order_type=order_type,
        order_date=date.today(),
        due_date=date.today(),
        lines=[
            {
                "product_id": product.id,
                "quantity": quantity,
                "unit_price": 20,
                "unit": "unit",
            }
        ],
        actor="dev",
    )


def test_sales_order_reserves_and_ships_against_append_only_ledger():
    coman, commercial, org, facility, product = _setup()
    customer = commercial.create_trade_partner(
        org.id, name="Retail Customer", partner_type="customer", actor="dev"
    )
    lot = coman.create_inventory_lot(
        org.id,
        facility.id,
        product_id=product.id,
        lot_code="FG-LOT-1",
        actor="dev",
        opening_quantity=20,
        unit="unit",
    )
    order = _order(
        commercial,
        org,
        facility,
        product,
        customer,
        order_type="sales",
        number="SO-1",
    )
    line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    commercial.confirm_order(
        order.id,
        organization_id=org.id,
        facility_id=facility.id,
        actor="dev",
    )
    commercial.allocate_lot(
        organization_id=org.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="dev",
    )
    transaction = commercial.post_fulfillment(
        organization_id=org.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="dev",
    )

    assert transaction.quantity_delta == -10
    assert coman.inventory_balance(org.id, lot.id) == 10
    assert commercial.list_orders(org.id, facility.id)[0].status == "fulfilled"
    assert commercial.list_allocations(org.id, facility.id)[0].status == "fulfilled"


def test_sales_fulfillment_requires_a_reservation_and_available_inventory():
    coman, commercial, org, facility, product = _setup()
    customer = commercial.create_trade_partner(
        org.id, name="Retail Customer", partner_type="customer", actor="dev"
    )
    lot = coman.create_inventory_lot(
        org.id,
        facility.id,
        product_id=product.id,
        lot_code="FG-LOT-2",
        actor="dev",
        opening_quantity=5,
        unit="unit",
    )
    order = _order(
        commercial,
        org,
        facility,
        product,
        customer,
        order_type="sales",
        number="SO-2",
        quantity=10,
    )
    line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    commercial.confirm_order(
        order.id,
        organization_id=org.id,
        facility_id=facility.id,
        actor="dev",
    )

    with pytest.raises(ValueError, match="reserved"):
        commercial.post_fulfillment(
            organization_id=org.id,
            facility_id=facility.id,
            order_line_id=line.id,
            lot_id=lot.id,
            quantity=1,
            actor="dev",
        )
    with pytest.raises(ValueError, match="unreserved"):
        commercial.allocate_lot(
            organization_id=org.id,
            facility_id=facility.id,
            order_line_id=line.id,
            lot_id=lot.id,
            quantity=6,
            actor="dev",
        )


def test_purchase_receipt_increases_inventory_and_completes_order():
    coman, commercial, org, facility, product = _setup()
    vendor = commercial.create_trade_partner(
        org.id, name="Licensed Vendor", partner_type="vendor", actor="dev"
    )
    lot = coman.create_inventory_lot(
        org.id,
        facility.id,
        product_id=product.id,
        lot_code="RECEIVING-1",
        actor="dev",
        unit="unit",
    )
    order = _order(
        commercial,
        org,
        facility,
        product,
        vendor,
        order_type="purchase",
        number="PO-1",
    )
    line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    commercial.confirm_order(
        order.id,
        organization_id=org.id,
        facility_id=facility.id,
        actor="dev",
    )
    commercial.post_fulfillment(
        organization_id=org.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="dev",
    )

    assert coman.inventory_balance(org.id, lot.id) == 10
    assert commercial.list_orders(org.id, facility.id)[0].status == "fulfilled"


def test_cross_tenant_partners_and_orders_are_not_visible_or_usable():
    coman, commercial, org, facility, product = _setup()
    other = coman.create_organization("Other Tenant")
    other_facility = coman.create_facility(other.id, "Other", "OTHER")
    other_product = coman.create_product(
        other.id,
        sku="OTHER",
        name="Other Product",
        item_type="finished_good",
        base_unit="unit",
        actor="dev",
    )
    hidden_partner = commercial.create_trade_partner(
        other.id, name="Hidden Vendor", partner_type="vendor", actor="dev"
    )
    _order(
        commercial,
        other,
        other_facility,
        other_product,
        hidden_partner,
        order_type="purchase",
        number="PO-HIDDEN",
    )

    assert commercial.list_trade_partners(org.id) == []
    assert commercial.list_orders(org.id, facility.id) == []
    with pytest.raises(ValueError, match="not found"):
        _order(
            commercial,
            org,
            facility,
            product,
            hidden_partner,
            order_type="purchase",
            number="PO-CROSS",
        )


def test_cancel_releases_active_allocations_and_metrics_are_consistent():
    coman, commercial, org, facility, product = _setup()
    customer = commercial.create_trade_partner(
        org.id, name="Customer", partner_type="customer", actor="dev"
    )
    lot = coman.create_inventory_lot(
        org.id,
        facility.id,
        product_id=product.id,
        lot_code="FG-LOT-3",
        actor="dev",
        opening_quantity=25,
        unit="unit",
    )
    order = _order(
        commercial,
        org,
        facility,
        product,
        customer,
        order_type="sales",
        number="SO-3",
    )
    line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    commercial.confirm_order(
        order.id,
        organization_id=org.id,
        facility_id=facility.id,
        actor="dev",
    )
    commercial.allocate_lot(
        organization_id=org.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="dev",
    )
    commercial.cancel_order(
        order.id,
        organization_id=org.id,
        facility_id=facility.id,
        actor="dev",
    )

    assert commercial.list_allocations(org.id, facility.id)[0].status == "released"
    saved_orders = commercial.list_orders(org.id, facility.id)
    saved_lines = commercial.list_order_lines(org.id)
    metrics = commercial_dashboard_metrics(saved_orders, saved_lines, inventory_value=200)
    assert metrics["inventory_value"] == 200
    assert metrics["open_orders"] == 0
