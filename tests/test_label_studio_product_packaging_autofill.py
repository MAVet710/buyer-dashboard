from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.product_master.packaging import ProductPackagingService


def test_label_studio_uses_product_master_packaging_for_net_contents():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Package Label Org", slug="package-label-org")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Manufacturing",
            code="MFG",
            license_number="MP-TEST-1",
            production_enabled=True,
        )
        product = Product(
            organization_id=org.id,
            sku="FLOWER-35",
            name="Copper Kush Flower",
            item_type="finished_good",
            base_unit="unit",
        )
        session.add_all([facility, product])
        session.flush()
        ProductPackagingService.upsert(
            session,
            organization_id=org.id,
            product_id=product.id,
            net_content=3.5,
            net_content_unit="g",
            units_per_package=1,
            sellable_unit="each",
            case_pack=24,
        )
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="FLOWER-35-LOT",
            compliance_package_id="1A4000000000000000035000",
            location_code="FINISHED-GOODS",
            status="available",
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=org.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="package_output",
                quantity_delta=24,
                unit="unit",
                actor="operator",
            )
        )
        org_id, facility_id, lot_id = org.id, facility.id, lot.id

    source = LabelInventoryService(engine).get_source(org_id, facility_id, lot_id)
    assert source["label"]["net_contents"] == "3.5 g"
    assert source["label"]["package_id"] == "1A4000000000000000035000"
    assert source["on_hand"] == 24


def test_lot_specific_declared_net_contents_override_product_default():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Override Label Org", slug="override-label-org")
        session.add(org)
        session.flush()
        facility = Facility(organization_id=org.id, name="Manufacturing", code="MFG")
        product = Product(
            organization_id=org.id,
            sku="MULTIPACK",
            name="Pre-Roll Multipack",
            item_type="finished_good",
            base_unit="unit",
        )
        session.add_all([facility, product])
        session.flush()
        ProductPackagingService.upsert(
            session,
            organization_id=org.id,
            product_id=product.id,
            net_content=3.5,
            net_content_unit="g",
        )
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="MULTIPACK-SPECIAL",
            compliance_package_id="PKG-MULTIPACK",
            location_code="FINISHED-GOODS",
            status="available",
            notes='{"declared_net_contents":"5 x 0.7 g pre-rolls / 3.5 g total"}',
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=org.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="package_output",
                quantity_delta=12,
                unit="unit",
                actor="operator",
            )
        )
        org_id, facility_id, lot_id = org.id, facility.id, lot.id

    source = LabelInventoryService(engine).get_source(org_id, facility_id, lot_id)
    assert source["label"]["net_contents"] == "5 x 0.7 g pre-rolls / 3.5 g total"
