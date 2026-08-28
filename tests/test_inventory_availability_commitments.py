from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine

from backend.app.services.inventory import InventoryQueryService
from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.inventory_availability.service import InventoryAvailabilityService


def _setup(quantity: float = 100):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)
    organization = coman.create_organization("Availability QA")
    facility = coman.create_facility(organization.id, "Manufacturing + Wholesale", "MFG-WHOLESALE")
    product = coman.create_product(
        organization.id,
        sku="FG-WHOLESALE",
        name="Finished Wholesale Product",
        item_type="finished_good",
        base_unit="case",
        unit_cost=20,
        retail_price=60,
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="LOT-AVAIL-1",
        actor="dev",
        opening_quantity=quantity,
        unit="case",
    )
    customer = commercial.create_trade_partner(
        organization.id,
        name="Retail Customer",
        partner_type="customer",
        actor="dev",
    )
    return engine, coman, commercial, organization, facility, product, lot, customer


def _sales_order(commercial, organization, facility, product, customer, *, number: str, quantity: float):
    return commercial.create_order(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=customer.id,
        order_number=number,
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{"product_id": product.id, "quantity": quantity, "unit": "case", "unit_price": 50}],
        actor="sales",
    )


def test_confirmed_wholesale_order_reduces_active_inventory_before_lot_allocation():
    engine, _, commercial, organization, facility, product, lot, customer = _setup()
    order = _sales_order(commercial, organization, facility, product, customer, number="SO-COMMIT", quantity=30)

    before = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert before["on_hand"] == 100
    assert before["wholesale_committed"] == 0
    assert before["available"] == 100

    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")

    after = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert after["wholesale_committed"] == 30
    assert after["wholesale_reserved"] == 0
    assert after["reserved"] == 30
    assert after["available"] == 70
    assert any(claim["source"] == "wholesale" and claim["reference"] == "SO-COMMIT" for claim in after["claims"])

    active = InventoryQueryService(engine).list_production_packages(organization.id, facility.id)
    row = active.items[0]
    assert row.available == 70
    assert row.reserved == 30
    assert row.attention == "Committed"


def test_lot_allocation_converts_soft_wholesale_commitment_without_double_counting():
    engine, _, commercial, organization, facility, product, lot, customer = _setup()
    order = _sales_order(commercial, organization, facility, product, customer, number="SO-ALLOC", quantity=30)
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]

    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=30,
        actor="warehouse",
    )

    row = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert row["wholesale_committed"] == 0
    assert row["wholesale_reserved"] == 30
    assert row["reserved"] == 30
    assert row["available"] == 70


def test_production_reservation_cannot_consume_quantity_committed_to_wholesale():
    engine, coman, commercial, organization, facility, product, lot, customer = _setup()
    order = _sales_order(commercial, organization, facility, product, customer, number="SO-PROTECT", quantity=30)
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    production = coman.create_production_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number="PROD-1",
        work_type="internal",
        product_name="Pack finished goods",
        product_format="case",
        requested_units=1,
        actor="planner",
    )

    with pytest.raises(ValueError, match="organization-wide"):
        coman.reserve_material(
            organization.id,
            facility.id,
            production_order_id=production.id,
            lot_id=lot.id,
            quantity=71,
            unit="case",
            actor="planner",
        )

    reservation = coman.reserve_material(
        organization.id,
        facility.id,
        production_order_id=production.id,
        lot_id=lot.id,
        quantity=70,
        unit="case",
        actor="planner",
    )
    assert reservation.quantity == 70
    snapshot = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert snapshot["production_reserved"] == 70
    assert snapshot["wholesale_committed"] == 30
    assert snapshot["available"] == 0


def test_commercial_lot_allocation_respects_production_reservation():
    engine, coman, commercial, organization, facility, product, lot, customer = _setup()
    production = coman.create_production_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number="PROD-2",
        work_type="internal",
        product_name="Internal pack",
        product_format="case",
        requested_units=1,
        actor="planner",
    )
    coman.reserve_material(
        organization.id,
        facility.id,
        production_order_id=production.id,
        lot_id=lot.id,
        quantity=60,
        unit="case",
        actor="planner",
    )
    order = _sales_order(commercial, organization, facility, product, customer, number="SO-BLOCKED", quantity=50)
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]

    with pytest.raises(ValueError, match="Production and Wholesale claims"):
        commercial.allocate_lot(
            organization_id=organization.id,
            facility_id=facility.id,
            order_line_id=line.id,
            lot_id=lot.id,
            quantity=50,
            actor="warehouse",
        )

    snapshot = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)
    assert snapshot["by_product"][product.id]["uncovered_commitment"] == 10
    assert snapshot["by_lot"][lot.id]["available"] == 0


def test_cancelled_wholesale_order_releases_soft_and_hard_inventory_claims():
    engine, _, commercial, organization, facility, product, lot, customer = _setup()
    order = _sales_order(commercial, organization, facility, product, customer, number="SO-CANCEL", quantity=25)
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]
    commercial.allocate_lot(
        organization_id=organization.id,
        facility_id=facility.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="warehouse",
    )
    committed = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert committed["reserved"] == 25
    assert committed["available"] == 75

    commercial.cancel_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="sales")
    released = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert released["wholesale_committed"] == 0
    assert released["wholesale_reserved"] == 0
    assert released["reserved"] == 0
    assert released["available"] == 100
