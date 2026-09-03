import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Organization, Product
from modules.product_master.packaging import ProductPackagingService


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _product(engine):
    with Session(engine) as session, session.begin():
        org = Organization(name="Label Layout Org", slug="label-layout-org")
        session.add(org)
        session.flush()
        product = Product(
            organization_id=org.id,
            sku="FLOWER-35",
            name="Flower 3.5g",
            item_type="finished_good",
            base_unit="unit",
        )
        session.add(product)
        session.flush()
        return org.id, product.id


def test_compact_split_can_be_one_source_for_flower_or_two_sources_for_duo():
    engine = _engine()
    organization_id, product_id = _product(engine)
    with Session(engine) as session, session.begin():
        flower = ProductPackagingService.upsert(
            session,
            organization_id=organization_id,
            product_id=product_id,
            net_content=3.5,
            net_content_unit="g",
            label_layout="compact_split",
            label_width_in=3.5,
            label_height_in=2.1,
            label_source_count=1,
        )
        assert flower.label_layout == "compact_split"
        assert flower.label_source_count == 1

        duo = ProductPackagingService.upsert(
            session,
            organization_id=organization_id,
            product_id=product_id,
            net_content=7,
            net_content_unit="g",
            label_layout="compact_split",
            label_width_in=3.5,
            label_height_in=2.1,
            label_source_count=2,
        )
        assert duo.label_layout == "compact_split"
        assert duo.label_source_count == 2


def test_two_sources_are_rejected_for_non_split_layouts():
    engine = _engine()
    organization_id, product_id = _product(engine)
    with Session(engine) as session, session.begin():
        with pytest.raises(ValueError, match="Two-source labels require the compact split layout"):
            ProductPackagingService.upsert(
                session,
                organization_id=organization_id,
                product_id=product_id,
                net_content=28,
                net_content_unit="g",
                label_layout="bulk_barcode",
                label_source_count=2,
            )
