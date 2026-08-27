from __future__ import annotations

from sqlalchemy import create_engine

from modules.coman.models import Base
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commerce_storefronts.service import CommerceStorefrontService


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
