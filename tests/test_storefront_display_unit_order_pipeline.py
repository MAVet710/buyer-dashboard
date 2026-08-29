from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commerce_storefronts.sales_units import StorefrontProductSalesUnit
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.inventory_availability.service import InventoryAvailabilityService


def test_display_unit_order_is_durable_approval_request_and_normalizes_on_approval():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Storefront Pipeline QA")
    facility = coman.create_facility(organization.id, "Manufacturing + Wholesale", "PIPELINE-QA")
    product = coman.create_product(
        organization.id,
        sku="BULK-LB-QA",
        name="Bulk Flower QA",
        item_type="cannabis",
        base_unit="g",
        unit_cost=0.01,
        retail_price=0.03,
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="BULK-LB-LOT",
        actor="dev",
        opening_quantity=907.18474,
        unit="g",
    )
    with Session(engine) as session, session.begin():
        row = session.get(InventoryLot, lot.id)
        row.notes = json.dumps({"lab_testing_state": "Passed", "coa_reference": "COA-LB-QA"})

    service = WholesaleCommerceStorefrontService(engine)
    storefront = service.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Display Unit QA",
        subdomain="display-unit-qa",
        published=True,
    )
    service.set_products(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        products=[{
            "product_id": product.id,
            "price_usd": 0.02,
            "minimum_quantity": 453.59237,
            "case_quantity": 453.59237,
        }],
    )
    with Session(engine) as session, session.begin():
        session.add(StorefrontProductSalesUnit(
            organization_id=organization.id,
            storefront_id=storefront.id,
            product_id=product.id,
            sales_unit="lb",
            updated_by="admin",
        ))

    catalog = service.public_catalog("display-unit-qa")
    item = catalog["catalog"][0]
    assert item["unit"] == "lb"
    assert item["base_unit"] == "g"
    assert item["available"] == pytest.approx(2.0)
    assert item["minimum_quantity"] == pytest.approx(1.0)
    assert item["case_quantity"] == pytest.approx(1.0)
    assert item["price_usd"] == pytest.approx(9.0718474)

    request = service.submit_order_request(
        slug="display-unit-qa",
        buyer_company="Licensed Retailer",
        buyer_license="MR-PENDING-123",
        buyer_contact="Buyer",
        buyer_email="buyer@example.com",
        lines=[{"product_id": product.id, "quantity": 1.0}],
    )
    assert request.status == "submitted"

    approval_queue = service.list_order_requests(organization.id, facility.id)
    pending = [row for row in approval_queue if row["status"] == "submitted"]
    assert [row["id"] for row in pending] == [request.id]
    assert pending[0]["buyer_company"] == "Licensed Retailer"
    assert pending[0]["lines"][0]["quantity"] == pytest.approx(1.0)
    assert pending[0]["lines"][0]["unit"] == "lb"

    before = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert before["wholesale_committed"] == 0

    approved = service.approve_order_request(
        organization_id=organization.id,
        facility_id=facility.id,
        request_id=request.id,
        actor="sales-manager",
    )
    assert approved["order_status"] == "confirmed"

    after = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert after["wholesale_committed"] == pytest.approx(453.59237)
    assert after["available"] == pytest.approx(453.59237)
