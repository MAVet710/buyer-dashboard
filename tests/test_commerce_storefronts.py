from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commerce_storefronts.service import CommerceStorefrontService


ROOT = Path(__file__).resolve().parents[1]


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Storefront QA")
    facility = coman.create_facility(organization.id, "Wholesale", "WHOLESALE")
    return engine, coman, organization, facility


def test_hosted_storefront_is_subdomain_branded_and_approval_gated():
    engine, coman, organization, facility = _setup()
    product = coman.create_product(
        organization.id,
        sku="PR-10PK",
        name="GMO Pre-Roll 10 Pack",
        item_type="finished_good",
        base_unit="case",
        unit_cost=45,
        retail_price=100,
        actor="dev",
    )
    coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="LOT-WEB-1",
        actor="dev",
        opening_quantity=24,
        unit="case",
    )
    service = CommerceStorefrontService(engine)
    storefront = service.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Zero Hour Cannabis Co.",
        subdomain="zerohour",
        headline="Wholesale drop",
        published=True,
    )
    service.set_products(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        products=[{
            "product_id": product.id,
            "price_usd": 80,
            "minimum_quantity": 2,
            "case_quantity": 2,
            "featured": True,
            "active": True,
            "sort_order": 0,
        }],
    )

    public = service.public_catalog("zerohour")
    assert storefront.subdomain == "zerohour"
    assert public["storefront"]["url"] == "https://zerohour.doobielogic.io"
    assert public["catalog"][0]["available"] == 24
    assert public["catalog"][0]["price_usd"] == 80

    request = service.submit_order_request(
        slug="zerohour",
        buyer_company="Licensed Retailer",
        buyer_license="MR999999",
        buyer_contact="Retail Buyer",
        buyer_email="buyer@example.com",
        lines=[{"product_id": product.id, "quantity": 4}],
        purchase_order_reference="PO-88",
    )
    assert request.status == "submitted"
    assert CommercialRepository(engine).list_orders(organization.id, facility.id) == []

    approved = service.approve_order_request(
        organization_id=organization.id,
        facility_id=facility.id,
        request_id=request.id,
        actor="sales-manager",
    )
    orders = CommercialRepository(engine).list_orders(organization.id, facility.id)
    assert approved["order_id"] == orders[0].id
    assert approved["request"]["status"] == "approved"
    assert orders[0].external_reference == "PO-88"
    assert orders[0].created_by == "sales-manager"
    assert CommercialRepository(engine).list_order_lines(organization.id, order_id=orders[0].id)[0].unit_price == 80


def test_storefront_catalog_and_orders_stay_facility_and_tenant_scoped():
    engine, coman, organization, facility = _setup()
    other = coman.create_organization("Other Brand")
    other_facility = coman.create_facility(other.id, "Other", "OTHER")
    product = coman.create_product(organization.id, sku="OURS", name="Our Product", item_type="finished_good", base_unit="unit", retail_price=10, actor="dev")
    hidden = coman.create_product(other.id, sku="HIDDEN", name="Hidden Product", item_type="finished_good", base_unit="unit", retail_price=999, actor="dev")
    coman.create_inventory_lot(organization.id, facility.id, product_id=product.id, lot_code="OURS-1", actor="dev", opening_quantity=10, unit="unit")
    coman.create_inventory_lot(other.id, other_facility.id, product_id=hidden.id, lot_code="HIDDEN-1", actor="dev", opening_quantity=999, unit="unit")
    service = CommerceStorefrontService(engine)
    service.upsert_storefront(organization_id=organization.id, facility_id=facility.id, actor="admin", display_name="Ours", subdomain="ours", published=True)
    service.set_products(organization_id=organization.id, facility_id=facility.id, actor="admin", products=[{"product_id": product.id, "price_usd": 8}])

    public = service.public_catalog("ours")
    assert [row["sku"] for row in public["catalog"]] == ["OURS"]
    snapshot = service.admin_snapshot(other.id, other_facility.id)
    assert snapshot["storefront"] is None
    assert snapshot["pending_orders"] == []


def test_reserved_doobielogic_subdomain_is_rejected():
    engine, _, organization, facility = _setup()
    service = CommerceStorefrontService(engine)
    try:
        service.upsert_storefront(organization_id=organization.id, facility_id=facility.id, actor="admin", display_name="Bad", subdomain="ops", published=True)
    except ValueError as exc:
        assert "reserved" in str(exc).lower()
    else:
        raise AssertionError("Reserved DoobieLogic host must not be assignable to a customer storefront")


def test_cowboy_kush_storefront_is_discoverable_collectible_and_request_only():
    page = (ROOT / "frontend/src/pages/StorefrontPage.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/cowboy-storefront.css").read_text(encoding="utf-8")
    main = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")

    # Cowboy Kush must be reachable by its exact hosted storefront slug while generic
    # storefront rendering remains present for every other customer.
    assert 'slug.trim().toLowerCase() === "cowboykush"' in page
    assert 'data.storefront.subdomain.trim().toLowerCase() === "cowboykush"' in page
    assert 'const storefrontSlug = pathStorefrontMatch ? decodeURIComponent(pathStorefrontMatch[1]) : hostStorefront;' in main
    assert 'import "./cowboy-storefront.css";' in main
    assert 'return <div className="storefront-shell" style={theme}>' in page

    # This is a purpose-built wholesale ordering landing page, not a clone of the
    # marketing site's story/farm/blog navigation.
    assert "ROOTED IN TRADITION · GROWN FOR ADVENTURE" in page
    assert "Premium Massachusetts" in page
    assert ">Wholesale</a>" in page
    assert "Our Story" not in page
    assert "Our Farms" not in page
    assert "Field Notes" not in page

    # Collectible cards expose operationally real storefront data rather than
    # fabricated potency/effect claims.
    for label in ("SKU", "Pack size", "Case qty", "Wholesale", "Min order", "Status"):
        assert label in page
    assert "item.sku" in page
    assert "item.available" in page
    assert "item.price_usd" in page
    assert "item.minimum_quantity" in page
    assert "item.case_quantity" in page
    assert "THC" not in page
    assert "terpene" not in page.lower()

    # Keep the existing approval-gated DoobieCommerce request endpoint. The
    # public page never converts a submission straight into an operational order.
    assert '/api/v1/commerce-storefronts/${encodeURIComponent(slug)}/orders' in page
    assert "Submit order request" in page
    assert "Inventory is not deducted until their team reviews the request." in page

    # Cowboy styling is strictly scoped and stays usable at tablet/phone widths.
    assert ".cowboy-storefront" in css
    assert "--cowboy-slate:#536f80" in css
    assert "--cowboy-cream:#e8e4dc" in css
    assert "--cowboy-navy:#071d32" in css
    assert "--cowboy-gold:#b58b3d" in css
    assert "@media(max-width:980px)" in css
    assert "@media(max-width:720px)" in css
    assert ".cowboy-storefront .cowboy-cart{position:static}" in css


def test_item_checkbox_groups_offer_select_all_controls():
    storefront_manager = (ROOT / "frontend/src/components/CommerceStorefrontManager.tsx").read_text(encoding="utf-8")
    admin = (ROOT / "frontend/src/pages/AdminPage.tsx").read_text(encoding="utf-8")

    assert 'aria-label="Select all storefront products"' in storefront_manager
    assert "current.map(item=>({...item,selected:e.target.checked}))" in storefront_manager
    assert 'aria-label="Select all facilities"' in admin
    assert "facilities.map(row=>row.id)" in admin
