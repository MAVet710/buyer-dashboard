import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product


def _seed():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="Append Only", slug="append-only")
        session.add(organization)
        session.flush()
        facility = Facility(organization_id=organization.id, name="Facility", code="APPEND")
        product = Product(
            organization_id=organization.id,
            sku="APPEND-SKU",
            name="Material",
            item_type="cannabis",
            base_unit="g",
        )
        session.add_all([facility, product])
        session.flush()
        lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="APPEND-LOT",
            status="available",
        )
        session.add(lot)
        session.flush()
        tx = InventoryTransaction(
            organization_id=organization.id,
            facility_id=facility.id,
            lot_id=lot.id,
            transaction_type="receipt",
            quantity_delta=10,
            unit="g",
            actor="seed",
        )
        session.add(tx)
        session.commit()
        return engine, tx.id


def test_posted_inventory_transaction_cannot_be_edited():
    engine, tx_id = _seed()
    with Session(engine) as session:
        tx = session.get(InventoryTransaction, tx_id)
        tx.quantity_delta = 99
        with pytest.raises(ValueError, match="append-only"):
            session.commit()


def test_posted_inventory_transaction_cannot_be_deleted():
    engine, tx_id = _seed()
    with Session(engine) as session:
        tx = session.get(InventoryTransaction, tx_id)
        session.delete(tx)
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
