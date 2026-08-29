from __future__ import annotations

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.routers.storefronts import PublicOrderPayload, StorefrontProductPayload
from modules.coman.models import Base, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commerce_storefronts.service import _decode_po_attachment, _effective_price, _quantity_breaks
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.commercial.repository import CommercialRepository


def _setup_storefront():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Storefront Order Terms QA")
    facility = coman.create_facility(organization.id, "Wholesale Facility", "WHOLESALE-QA")
    product = coman.create_product(
        organization.id,
        sku="VOL-CASE",
        name="Volume Case",
        item_type="finished_good",
        base_unit="case",
        retail_price=100,
        actor="dev",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="VOL-LOT",
        actor="dev",
        opening_quantity=100,
        unit="case",
    )
    with Session(engine) as session, session.begin():
        row = session.get(InventoryLot, lot.id)
        row.notes = '{"lab_testing_state":"Passed","coa_reference":"COA-VOL","thca_percent":25,"tac_percent":28,"total_terpenes_percent":2}'

    service = WholesaleCommerceStorefrontService(engine)
    service.upsert_storefront(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        display_name="Volume QA",
        subdomain="volume-qa",
        published=True,
    )
    service.set_products(
        organization_id=organization.id,
        facility_id=facility.id,
        actor="admin",
        products=[
            {
                "product_id": product.id,
                "price_usd": 80,
                "minimum_quantity": 2,
                "case_quantity": 2,
                "quantity_breaks": [
                    {"minimum_quantity": 20, "price_usd": 65},
                    {"minimum_quantity": 10, "price_usd": 72},
                ],
            }
        ],
    )
    return engine, coman, organization, facility, product, service


def _pdf_payload() -> tuple[str, str, str, bytes]:
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    return "buyer-po.pdf", "application/pdf", base64.b64encode(content).decode("ascii"), content


def test_quantity_breaks_normalize_and_effective_price_uses_highest_qualifying_tier():
    rows = _quantity_breaks(
        [
            {"minimum_quantity": 20, "price_usd": 65},
            {"minimum_quantity": 10, "price_usd": 72},
        ],
        minimum_quantity=2,
        case_quantity=2,
    )
    assert rows == [
        {"minimum_quantity": 10.0, "price_usd": 72.0},
        {"minimum_quantity": 20.0, "price_usd": 65.0},
    ]
    assert _effective_price(80, rows, 8) == (80.0, "base")
    assert _effective_price(80, rows, 10) == (72.0, "quantity_break")
    assert _effective_price(80, rows, 24) == (65.0, "quantity_break")


def test_quantity_break_contract_rejects_duplicate_and_misaligned_thresholds():
    with pytest.raises(ValidationError, match="minimums must be unique"):
        StorefrontProductPayload.model_validate(
            {
                "product_id": "product-1",
                "price_usd": 80,
                "minimum_quantity": 2,
                "case_quantity": 2,
                "quantity_breaks": [
                    {"minimum_quantity": 10, "price_usd": 72},
                    {"minimum_quantity": 10, "price_usd": 70},
                ],
            }
        )
    with pytest.raises(ValueError, match="align to the listing case quantity"):
        _quantity_breaks([{"minimum_quantity": 9, "price_usd": 72}], minimum_quantity=2, case_quantity=2)


def test_server_applies_volume_price_and_persists_delivery_window():
    _engine, _coman, _organization, _facility, product, service = _setup_storefront()
    request = service.submit_order_request(
        slug="volume-qa",
        buyer_company="Buyer One",
        buyer_contact="Purchasing",
        buyer_email="buyer1@example.com",
        lines=[{"product_id": product.id, "quantity": 20}],
        requested_delivery_window="Tuesday 9 AM–1 PM",
    )
    snapshot = service.list_order_requests(request.organization_id, request.facility_id)[0]
    assert request.estimated_subtotal == 1300
    assert snapshot["estimated_subtotal"] == 1300
    assert snapshot["lines"][0]["price_usd"] == 65
    assert snapshot["lines"][0]["base_price_usd"] == 80
    assert snapshot["lines"][0]["price_source"] == "quantity_break"
    assert snapshot["requested_delivery_window"] == "Tuesday 9 AM–1 PM"


def test_po_attachment_validation_rejects_disguised_or_oversize_files():
    fake_pdf = base64.b64encode(b"<html>not a pdf</html>").decode("ascii")
    with pytest.raises(ValidationError, match="contents do not match"):
        PublicOrderPayload.model_validate(
            {
                "buyer_company": "Buyer",
                "buyer_contact": "Person",
                "buyer_email": "buyer@example.com",
                "lines": [{"product_id": "p1", "quantity": 1}],
                "purchase_order_attachment_name": "fake.pdf",
                "purchase_order_attachment_type": "application/pdf",
                "purchase_order_attachment_base64": fake_pdf,
            }
        )

    oversized = base64.b64encode(b"%PDF-" + (b"x" * (3 * 1024 * 1024))).decode("ascii")
    with pytest.raises(ValueError, match="3 MB or smaller"):
        _decode_po_attachment("too-big.pdf", "application/pdf", oversized)


def test_po_attachment_is_private_tenant_scoped_and_public_status_does_not_expose_content():
    _engine, coman, organization, facility, product, service = _setup_storefront()
    name, content_type, encoded, content = _pdf_payload()
    request = service.submit_order_request(
        slug="volume-qa",
        buyer_company="Buyer Two",
        buyer_license="MR-UNVERIFIED",
        buyer_contact="Purchasing",
        buyer_email="buyer2@example.com",
        lines=[{"product_id": product.id, "quantity": 2}],
        purchase_order_reference="PO-200",
        purchase_order_attachment_name=name,
        purchase_order_attachment_type=content_type,
        purchase_order_attachment_base64=encoded,
    )

    internal = service.list_order_requests(organization.id, facility.id)[0]
    assert internal["purchase_order_attachment"]["file_name"] == name
    assert internal["purchase_order_attachment"]["byte_size"] == len(content)
    assert internal["license_verification"] == "supplied_unverified"

    public = service.public_order_status(slug="volume-qa", request_id=request.id, buyer_email="buyer2@example.com")
    assert "purchase_order_attachment" not in public
    assert "content" not in public

    downloaded = service.purchase_order_attachment(
        organization_id=organization.id,
        facility_id=facility.id,
        request_id=request.id,
    )
    assert downloaded["content"] == content
    assert downloaded["content_type"] == "application/pdf"

    other_org = coman.create_organization("Other Tenant")
    other_facility = coman.create_facility(other_org.id, "Other Facility", "OTHER-QA")
    with pytest.raises(ValueError, match="not found in this facility"):
        service.purchase_order_attachment(
            organization_id=other_org.id,
            facility_id=other_facility.id,
            request_id=request.id,
        )


def test_local_license_status_is_explicitly_not_external_verification():
    engine, _coman, organization, facility, product, service = _setup_storefront()
    CommercialRepository(engine).create_trade_partner(
        organization.id,
        name="Known Retailer",
        partner_type="customer",
        actor="admin",
        license_or_registration="MR-LOCAL-123",
    )
    service.submit_order_request(
        slug="volume-qa",
        buyer_company="Known Retailer",
        buyer_license="MR-LOCAL-123",
        buyer_contact="Known Buyer",
        buyer_email="known@example.com",
        lines=[{"product_id": product.id, "quantity": 2}],
    )
    service.submit_order_request(
        slug="volume-qa",
        buyer_company="No License Buyer",
        buyer_contact="No License",
        buyer_email="missing@example.com",
        lines=[{"product_id": product.id, "quantity": 2}],
    )
    rows = service.list_order_requests(organization.id, facility.id)
    by_email = {row["buyer_email"]: row for row in rows}
    assert by_email["known@example.com"]["license_verification"] == "matched_local_customer"
    assert by_email["missing@example.com"]["license_verification"] == "missing"
    assert "externally" not in by_email["known@example.com"]["license_verification"]


def test_storefront_final_gap_source_and_migration_contracts():
    page = Path("frontend/src/pages/StorefrontPage.tsx").read_text(encoding="utf-8")
    manager = Path("frontend/src/components/CommerceStorefrontManager.tsx").read_text(encoding="utf-8")
    migration = Path("migrations/versions/0051_storefront_order_terms.py").read_text(encoding="utf-8")

    assert '<option value="tac">Highest TAC</option>' in page
    assert "Volume pricing" in page
    assert "requested_delivery_window" in page
    assert "purchase_order_attachment_base64" in page
    assert "Local customer match" in manager
    assert "Supplied — not externally verified" in manager
    assert 'down_revision = "0050_regulatory_mappings"' in migration
    assert 'revision = "0051_storefront_order_terms"' in migration
    assert "commerce_storefront_order_attachments" in migration
    assert "quantity_breaks_json" in migration
