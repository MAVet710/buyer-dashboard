from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commerce_storefronts.intelligence import StorefrontWholesaleIntelligenceService
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.product_master.models import ProductMasterProfile

ROOT = Path(__file__).resolve().parents[1]


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Storefront V2 QA")
    facility = coman.create_facility(organization.id, "Manufacturing + Wholesale", "MFG-WHOLESALE")
    product = coman.create_product(organization.id, sku="GMO-35", name="GMO Flower 3.5g", item_type="finished_good", base_unit="case", retail_price=100, actor="dev")
    lot = coman.create_inventory_lot(organization.id, facility.id, product_id=product.id, lot_code="BATCH-A", actor="dev", opening_quantity=8, unit="case")
    with Session(engine) as session, session.begin():
        inventory = session.get(InventoryLot, lot.id)
        inventory.status = "available"
        inventory.notes = json.dumps({
            "lab_testing_state": "Passed",
            "coa_reference": "https://labs.example/coa-a.pdf",
            "coa_url": "https://labs.example/coa-a.pdf",
            "batch_name": "GMO A",
            "thca_percent": 27.4,
            "tac_percent": 31.2,
            "total_terpenes_percent": 2.83,
            "harvest_date": "2026-07-10",
            "production_date": "2026-07-20",
        })
        session.add(ProductMasterProfile(
            organization_id=organization.id,
            product_id=product.id,
            brand="QA Cannabis",
            category="Flower",
            strain="GMO",
            product_format="3.5g pre-packed flower",
            image_url="https://images.example/gmo.png",
            description="GMO wholesale flower",
        ))
    service = WholesaleCommerceStorefrontService(engine)
    service.upsert_storefront(organization_id=organization.id, facility_id=facility.id, actor="admin", display_name="QA Cannabis", subdomain="qa-v2", published=True)
    service.set_products(organization_id=organization.id, facility_id=facility.id, actor="admin", products=[{"product_id": product.id, "price_usd": 80, "minimum_quantity": 2, "case_quantity": 2, "featured": True}])
    return engine, coman, organization, facility, product, lot, service


def test_public_catalog_keeps_batch_lab_coa_and_product_master_data_together():
    _, _, _, _, product, lot, service = _setup()
    item = service.public_catalog("qa-v2")["catalog"][0]
    assert item["product_id"] == product.id
    assert item["strain"] == "GMO"
    assert item["category"] == "Flower"
    assert item["image_url"] == "https://images.example/gmo.png"
    assert item["availability_status"] == "in_stock"
    assert item["primary_batch"]["lot_id"] == lot.id
    assert item["primary_batch"]["coa_url"] == "https://labs.example/coa-a.pdf"
    assert item["primary_batch"]["thca_percent"] == 27.4
    assert item["primary_batch"]["tac_percent"] == 31.2
    assert item["primary_batch"]["terpenes_percent"] == 2.83
    assert item["primary_batch"]["harvested_at"] == "2026-07-10"
    assert item["primary_batch"]["produced_at"] == "2026-07-20"


def test_partial_approval_can_reduce_quantity_and_reprice_before_inventory_commitment():
    engine, _, organization, facility, product, _, service = _setup()
    request = service.submit_order_request(slug="qa-v2", buyer_company="Retailer", buyer_license="MR123", buyer_contact="Buyer", buyer_email="buyer@example.com", lines=[{"product_id": product.id, "quantity": 4}])
    result = service.approve_order_request(
        organization_id=organization.id,
        facility_id=facility.id,
        request_id=request.id,
        actor="sales-manager",
        review_note="Two cases approved at promo pricing.",
        approved_lines=[{"product_id": product.id, "quantity": 2, "price_usd": 70}],
    )
    assert result["request"]["approval_mode"] == "partial"
    assert result["request"]["estimated_subtotal"] == 140
    assert result["request"]["lines"][0]["requested_quantity"] == 4
    assert result["request"]["lines"][0]["quantity"] == 2
    order_line = CommercialRepository(engine).list_order_lines(organization.id, order_id=result["order_id"])[0]
    assert order_line.quantity == 2
    assert order_line.unit_price == 70


def test_public_order_tracking_is_bound_to_storefront_and_buyer_email():
    _, _, _, _, product, _, service = _setup()
    request = service.submit_order_request(slug="qa-v2", buyer_company="Retailer", buyer_contact="Buyer", buyer_email="buyer@example.com", lines=[{"product_id": product.id, "quantity": 2}])
    status = service.public_order_status(slug="qa-v2", request_id=request.id, buyer_email="buyer@example.com")
    assert status["status"] == "submitted"
    assert status["fulfillment_status"] == "awaiting_review"
    try:
        service.public_order_status(slug="qa-v2", request_id=request.id, buyer_email="other@example.com")
    except ValueError as exc:
        assert "not found" in str(exc).lower()
    else:
        raise AssertionError("Public order tracking must not disclose a request to a different email")


def test_wholesale_doobie_agent_uses_operational_storefront_truth():
    engine, _, organization, facility, product, _, service = _setup()
    service.submit_order_request(slug="qa-v2", buyer_company="Retailer", buyer_contact="Buyer", buyer_email="buyer@example.com", lines=[{"product_id": product.id, "quantity": 2}])
    intelligence = StorefrontWholesaleIntelligenceService(engine)
    approvals = intelligence.answer(organization.id, facility.id, "Which customer orders need approval?")
    terps = intelligence.answer(organization.id, facility.id, "Which batches have the strongest terpene profile?")
    assert approvals["kind"] == "orders_needing_approval"
    assert len(approvals["data"]) == 1
    assert terps["kind"] == "terpenes"
    assert terps["data"][0]["terpenes_percent"] == 2.83


def test_storefront_v2_frontend_contract_covers_browsing_cart_batch_and_agent_workflows():
    page = (ROOT / "frontend/src/pages/StorefrontPage.tsx").read_text(encoding="utf-8")
    manager = (ROOT / "frontend/src/components/CommerceStorefrontManager.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/storefront-commerce-v2.css").read_text(encoding="utf-8")
    for token in ("Search wholesale catalog", "Filter category", "Sort catalog", "Featured Drops", "View / download COA", "Sellable batch", "Check order status", "localStorage", "Coming soon", "Sold out"):
        assert token in page
    for token in ("Approve / apply changes", "Supplied — not externally verified", "Local customer match", "License missing", "DOOBIE AGENT · WHOLESALE", "Which manifests still need verification?", "Customer-specific pricing & terms"):
        assert token in manager
    assert ".commerce-v2-lab-strip" in css
    assert ".commerce-v2-batch-grid" in css
