from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.services.sandbox_sales import sync_sandbox_retail_sales
from modules.coman.models import Base, Facility, Organization, Product, RetailSale
from modules.data_hub_repository import DataHubRepository


def _engine_with_sandbox():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="DEV Sandbox", slug="dev-sandbox", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Sandbox Facility",
            code="SANDBOX",
            timezone_name="America/New_York",
            active=True,
        )
        session.add(facility)
        session.flush()
        products = [
            Product(
                organization_id=organization.id,
                sku="DL-FL-0001",
                name="Sandbox Flower",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=10.0,
                retail_price=30.0,
                active=True,
            ),
            Product(
                organization_id=organization.id,
                sku="DL-PR-0002",
                name="Sandbox Pre-Roll",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=4.0,
                retail_price=12.0,
                active=True,
            ),
        ]
        session.add_all(products)
        session.flush()
        organization_id = organization.id
        facility_id = facility.id
    return engine, organization_id, facility_id


def test_sync_sandbox_retail_sales_populates_canonical_ledger_and_is_idempotent():
    engine, organization_id, facility_id = _engine_with_sandbox()
    csv_payload = "\n".join(
        [
            "Product Name,Quantity Sold,Net Sales,Order ID,Order Time,SKU",
            "Sandbox Flower,2,54.00,ORD-1,2026-04-23 09:05:00,DL-FL-0001",
            "Sandbox Pre-Roll,3,32.40,ORD-2,2026-08-20 20:05:00,DL-PR-0002",
        ]
    ).encode("utf-8")
    DataHubRepository(engine).publish_source(
        organization_id=organization_id,
        facility_id=facility_id,
        dataset_key="sandbox_buyer_sales",
        dataset_label="DEV Sandbox · Buyer Sales",
        cache_key="_sandbox_buyer_sales",
        filename="demo_product_sales.csv",
        fingerprint="a" * 64,
        payload=csv_payload,
        inspection={"rows": 2, "columns": 6, "quality": "Sandbox source"},
        content_type="text/csv",
        imported_by="pytest",
    )

    first = sync_sandbox_retail_sales(engine)
    second = sync_sandbox_retail_sales(engine)

    assert first["synced"] is True
    assert first["rows"] == 2
    assert first["units"] == 5.0
    assert first["sales_window_days"] == 120
    assert second["synced"] is False
    assert second["reason"] == "already_current"

    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(RetailSale).where(
                    RetailSale.organization_id == organization_id,
                    RetailSale.facility_id == facility_id,
                )
            )
        )
        count = session.scalar(select(func.count(RetailSale.id)))

    assert count == 2
    assert {row.sku for row in rows} == {"DL-FL-0001", "DL-PR-0002"}
    assert sum(row.quantity for row in rows) == 5.0
    assert all(row.product_id for row in rows)
