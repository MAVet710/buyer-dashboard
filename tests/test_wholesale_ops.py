from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.inventory_availability.service import InventoryAvailabilityService


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Wholesale Ops QA")
    facility = coman.create_facility(organization.id, "Manufacturing + Wholesale", "MFG-WHOLESALE")
    return engine, coman, organization, facility


def _mark_coa(engine, lot_id: str, *, state: str, reference: str) -> None:
    with Session(engine) as session, session.begin():
        lot = session.get(InventoryLot, lot_id)
        lot.notes = json.dumps({"lab_testing_state": state, "coa_reference": reference})


def test_wholesale_inventory_requires_released_passed_coa_and_supports_bulk_and_retail_ready():
    engine, coman, organization, facility = _setup()
    bulk = coman.create_product(
        organization.id,
        sku="BULK-ROSIN",
        name="Bulk Live Rosin",
        item_type="cannabis",
        base_unit="g",
        unit_cost=8,
        retail_price=15,
        actor="dev",
    )
    retail = coman.create_product(
        organization.id,
        sku="PR-5PK",
        name="GMO Pre-Roll 5 Pack",
        item_type="finished_good",
        base_unit="case",
        unit_cost=25,
        retail_price=50,
        actor="dev",
    )
    blocked = coman.create_product(
        organization.id,
        sku="VAPE-BLOCKED",
        name="Vape Cart",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=12,
        retail_price=30,
        actor="dev",
    )
    bulk_lot = coman.create_inventory_lot(organization.id, facility.id, product_id=bulk.id, lot_code="BULK-1", actor="dev", opening_quantity=100, unit="g")
    retail_lot = coman.create_inventory_lot(organization.id, facility.id, product_id=retail.id, lot_code="PR-1", actor="dev", opening_quantity=20, unit="case")
    blocked_lot = coman.create_inventory_lot(organization.id, facility.id, product_id=blocked.id, lot_code="VAPE-1", actor="dev", opening_quantity=30, unit="unit")
    _mark_coa(engine, bulk_lot.id, state="TestPassed", reference="COA-BULK")
    _mark_coa(engine, retail_lot.id, state="Passed", reference="COA-RETAIL")
    _mark_coa(engine, blocked_lot.id, state="NotTested", reference="")

    service = WholesaleCommerceStorefrontService(engine)
    inventory = service.wholesale_inventory(organization.id, facility.id)

    assert {row["sku"] for row in inventory["items"]} == {"BULK-ROSIN", "PR-5PK"}
    assert {row["inventory_type"] for row in inventory["items"]} == {"bulk", "retail_ready"}
    assert inventory["summary"]["bulk_lots"] == 1
    assert inventory["summary"]["retail_ready_lots"] == 1
    assert inventory["summary"]["blocked_lots"] == 1
    assert inventory["blocked_items"][0]["sku"] == "VAPE-BLOCKED"
    assert "COA reference is missing" in inventory["blocked_items"][0]["blocked_reasons"]


def test_public_storefront_catalog_inherits_wholesale_coa_gate():
    engine, coman, organization, facility = _setup()
    passed = coman.create_product(organization.id, sku="PASSED", name="Passed Product", item_type="finished_good", base_unit="case", retail_price=100, actor="dev")
    blocked = coman.create_product(organization.id, sku="BLOCKED", name="Blocked Product", item_type="finished_good", base_unit="case", retail_price=100, actor="dev")
    passed_lot = coman.create_inventory_lot(organization.id, facility.id, product_id=passed.id, lot_code="PASS-1", actor="dev", opening_quantity=10, unit="case")
    blocked_lot = coman.create_inventory_lot(organization.id, facility.id, product_id=blocked.id, lot_code="BLOCK-1", actor="dev", opening_quantity=10, unit="case")
    _mark_coa(engine, passed_lot.id, state="Passed", reference="COA-PASS")
    _mark_coa(engine, blocked_lot.id, state="Failed", reference="COA-FAIL")

    service = WholesaleCommerceStorefrontService(engine)
    service.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Wholesale QA",
        subdomain="wholesale-qa",
        published=True,
    )
    service.set_products(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        products=[
            {"product_id": passed.id, "price_usd": 80},
            {"product_id": blocked.id, "price_usd": 80},
        ],
    )

    public = service.public_catalog("wholesale-qa")
    assert [row["sku"] for row in public["catalog"]] == ["PASSED"]


def test_storefront_submission_is_demand_only_and_approval_becomes_inventory_commitment():
    engine, coman, organization, facility = _setup()
    product = coman.create_product(
        organization.id,
        sku="APPROVAL-COMMIT",
        name="Approved Wholesale Case",
        item_type="finished_good",
        base_unit="case",
        retail_price=100,
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="APPROVAL-LOT",
        actor="dev",
        opening_quantity=10,
        unit="case",
    )
    _mark_coa(engine, lot.id, state="Passed", reference="COA-APPROVAL")

    service = WholesaleCommerceStorefrontService(engine)
    service.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Approval QA",
        subdomain="approval-qa",
        published=True,
    )
    service.set_products(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        products=[{"product_id": product.id, "price_usd": 80, "minimum_quantity": 1, "case_quantity": 1}],
    )

    request = service.submit_order_request(
        slug="approval-qa",
        buyer_company="Licensed Retailer",
        buyer_license="MR123",
        buyer_contact="Buyer",
        buyer_email="buyer@example.com",
        lines=[{"product_id": product.id, "quantity": 4}],
    )
    submitted = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert request.status == "submitted"
    assert submitted["wholesale_committed"] == 0
    assert submitted["available"] == 10

    approved = service.approve_order_request(
        organization_id=organization.id,
        facility_id=facility.id,
        request_id=request.id,
        actor="sales-manager",
    )
    committed = InventoryAvailabilityService(engine).facility_snapshot(organization.id, facility.id)["by_lot"][lot.id]
    assert approved["order_status"] == "confirmed"
    assert committed["wholesale_committed"] == 4
    assert committed["available"] == 6
