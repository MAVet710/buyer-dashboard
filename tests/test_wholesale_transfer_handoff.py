from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, InventoryTransaction
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.inventory_transfers.commercial_handoff import CommercialTransferHandoffService


def _setup():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    commercial = CommercialRepository(engine)
    org = coman.create_organization("Wholesale Transfer QA")
    source = coman.create_facility(org.id, "Manufacturing License", "MFG")
    destination = coman.create_facility(org.id, "Retail License", "RTL")
    product = coman.create_product(
        org.id,
        sku="BD-VAPE-1G",
        name="Blue Dream Vape 1g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=8,
        actor="dev",
    )
    customer = commercial.create_trade_partner(
        org.id,
        name="Licensed Retail Customer",
        partner_type="customer",
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        org.id,
        source.id,
        product_id=product.id,
        lot_code="BD-VAPE-LOT",
        compliance_package_id="PKG-BD-VAPE",
        actor="dev",
        opening_quantity=20,
        unit="unit",
    )
    order = commercial.create_order(
        organization_id=org.id,
        facility_id=source.id,
        partner_id=customer.id,
        order_number="SO-BD-001",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{"product_id": product.id, "quantity": 10, "unit_price": 20, "unit": "unit"}],
        actor="dev",
    )
    line = commercial.list_order_lines(org.id, order_id=order.id)[0]
    commercial.confirm_order(
        order.id,
        organization_id=org.id,
        facility_id=source.id,
        actor="dev",
    )
    commercial.allocate_lot(
        organization_id=org.id,
        facility_id=source.id,
        order_line_id=line.id,
        lot_id=lot.id,
        quantity=10,
        actor="dev",
    )
    return engine, coman, commercial, org, source, destination, lot, order, line


def test_wholesale_licensed_transfer_is_the_single_physical_decrement():
    engine, coman, commercial, org, source, destination, lot, order, line = _setup()

    result = CommercialTransferHandoffService(engine).dispatch(
        org.id,
        source.id,
        destination_facility_id=destination.id,
        manifest_reference="XFER-BD-001",
        external_transfer_id="SO-BD-001",
        lines=[{
            "source_lot_id": lot.id,
            "quantity": 10,
            "commercial_order_line_id": line.id,
        }],
        actor="dev",
    )

    assert result["status"] == "shipped"
    assert coman.inventory_balance(org.id, lot.id) == pytest.approx(10.0)
    assert commercial.list_orders(org.id, source.id)[0].status == "fulfilled"
    assert commercial.list_order_lines(org.id, order_id=order.id)[0].fulfilled_quantity == pytest.approx(10.0)
    allocation = commercial.list_allocations(org.id, source.id, order_id=order.id)[0]
    assert allocation.status == "fulfilled"
    assert allocation.fulfilled_quantity == pytest.approx(10.0)

    with Session(engine) as session:
        movements = list(
            session.scalars(
                select(InventoryTransaction)
                .where(InventoryTransaction.lot_id == lot.id)
                .order_by(InventoryTransaction.occurred_at)
            )
        )
    assert [row.transaction_type for row in movements] == ["receipt", "transfer_out"]
    transfer_out = movements[-1]
    assert transfer_out.quantity_delta == pytest.approx(-10.0)
    assert transfer_out.commercial_order_id == order.id
    assert transfer_out.commercial_order_line_id == line.id
    assert not any(row.transaction_type == "shipment" for row in movements)


def test_cancelling_unreceived_wholesale_transfer_restores_inventory_and_reservation():
    engine, coman, commercial, org, source, destination, lot, order, line = _setup()
    service = CommercialTransferHandoffService(engine)
    dispatched = service.dispatch(
        org.id,
        source.id,
        destination_facility_id=destination.id,
        manifest_reference="XFER-BD-CANCEL",
        lines=[{
            "source_lot_id": lot.id,
            "quantity": 10,
            "commercial_order_line_id": line.id,
        }],
        actor="dev",
    )

    cancelled = service.cancel(
        org.id,
        source.id,
        dispatched["id"],
        actor="dev",
        reason="State manifest cancelled before receipt",
    )

    assert cancelled["status"] == "cancelled"
    assert coman.inventory_balance(org.id, lot.id) == pytest.approx(20.0)
    order_after = commercial.list_orders(org.id, source.id)[0]
    line_after = commercial.list_order_lines(org.id, order_id=order.id)[0]
    allocation = commercial.list_allocations(org.id, source.id, order_id=order.id)[0]
    assert order_after.status == "allocated"
    assert line_after.fulfilled_quantity == pytest.approx(0.0)
    assert allocation.status == "reserved"
    assert allocation.fulfilled_quantity == pytest.approx(0.0)

    with Session(engine) as session:
        movements = list(session.scalars(select(InventoryTransaction).where(InventoryTransaction.lot_id == lot.id)))
    assert sorted((row.transaction_type, row.quantity_delta) for row in movements) == [
        ("receipt", 20.0),
        ("transfer_cancel_return", 10.0),
        ("transfer_out", -10.0),
    ]


def test_wholesale_transfer_cannot_claim_another_orders_reservation():
    engine, _coman, commercial, org, source, destination, lot, _order, line = _setup()
    second_customer = commercial.create_trade_partner(org.id, name="Second Customer", partner_type="customer", actor="dev")
    product = commercial.list_order_lines(org.id)[0].product_id
    second = commercial.create_order(
        organization_id=org.id,
        facility_id=source.id,
        partner_id=second_customer.id,
        order_number="SO-BD-002",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today(),
        lines=[{"product_id": product, "quantity": 5, "unit_price": 20, "unit": "unit"}],
        actor="dev",
    )
    second_line = commercial.list_order_lines(org.id, order_id=second.id)[0]
    commercial.confirm_order(second.id, organization_id=org.id, facility_id=source.id, actor="dev")

    with pytest.raises(ValueError, match="Reserve this exact package"):
        CommercialTransferHandoffService(engine).dispatch(
            org.id,
            source.id,
            destination_facility_id=destination.id,
            manifest_reference="XFER-WRONG-OWNER",
            lines=[{
                "source_lot_id": lot.id,
                "quantity": 1,
                "commercial_order_line_id": second_line.id,
            }],
            actor="dev",
        )

    allocation = commercial.list_allocations(org.id, source.id)[0]
    assert allocation.commercial_order_line_id == line.id
