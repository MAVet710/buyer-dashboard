from io import BytesIO

import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman import ComanRepository
from modules.coman.models import Base, Facility
from modules.inventory_quality import CoaDocumentService, LotQualityEvidence, parse_coa_pdf
from modules.product_master import ProductMasterRepository, ProductPackagingService


PACKAGE_ID = "1A4000000000000000001111"
OTHER_PACKAGE_ID = "1A4000000000000000002222"


def _coa_pdf(package_id: str = PACKAGE_ID, *, include_tag: bool = True) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    lines = [
        "Product Name: Copper Kush Flower",
        "Batch Number: CK-0901-A",
        "Testing Laboratory: Example Cannabis Lab",
        "Lab ID: COA-0901-A",
        "Date Tested: 08/30/2026",
        "Overall Status: Pass",
    ]
    if include_tag:
        lines.append(f"METRC Source Package ID: {package_id}")
    lines.extend(
        [
            "THCA | 31.20 %",
            "Delta-9 THC | 1.03 %",
            "CBGA | 1.23 %",
            "Beta-Myrcene | 0.68 %",
            "Limonene | 0.24 %",
            "Total THC | 28.40 %",
            "Total CBD | 0.00 %",
            "Total Cannabinoids | 31.90 %",
            "Total Terpenes | 2.40 %",
        ]
    )
    y = 760
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 22
    pdf.save()
    return buffer.getvalue()


def _setup():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    organization = coman.create_organization("COA Label Test")
    facility = coman.create_facility(organization.id, "COA Manufacturing", "COA-MFG")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.production_enabled = True
        row.commercial_enabled = True
        row.license_number = "MP281999"
        row.license_type = "manufacturing"
    product = coman.create_product(
        organization.id,
        sku="CK-FLR-35",
        name="Copper Kush Flower 3.5g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=8,
        retail_price=35,
        actor="qa",
    )
    master.update_profile(
        organization.id,
        product.id,
        actor="qa",
        brand="Cowboy Kush",
        category="Flower",
        subcategory="Flower Jar 3.5g",
        strain="Copper Kush",
        manufacturer="COA Manufacturing",
        product_format="Flower Jar 3.5g",
        retail_enabled=True,
        production_enabled=True,
    )
    with Session(engine) as session, session.begin():
        ProductPackagingService.upsert(
            session,
            organization_id=organization.id,
            product_id=product.id,
            net_content=3.5,
            net_content_unit="g",
            case_pack=24,
        )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="CK-0901-A",
        actor="qa",
        opening_quantity=48,
        unit="unit",
        location_code="FINISHED-GOODS",
        compliance_package_id=PACKAGE_ID,
    )
    return engine, organization, facility, product, lot


def test_parser_normalizes_coa_using_cannlytics_style_fields():
    parsed = parse_coa_pdf(_coa_pdf(), expected_package_id=PACKAGE_ID)
    assert parsed["metrc_source_id"] == PACKAGE_ID
    assert parsed["verification_state"] == "matched"
    assert parsed["product_name"] == "Copper Kush Flower"
    assert parsed["batch_number"] == "CK-0901-A"
    assert parsed["status"] == "pass"
    assert parsed["total_thc"] == 28.4
    assert parsed["total_cannabinoids"] == 31.9
    assert parsed["total_terpenes"] == 2.4
    by_key = {row["key"]: row for row in parsed["results"]}
    assert by_key["thca"]["value"] == 31.2
    assert by_key["delta_9_thc"]["value"] == 1.03
    assert by_key["beta_myrcene"]["value"] == 0.68
    assert by_key["limonene"]["value"] == 0.24


def test_fallback_rejects_a_coa_for_a_different_metrc_tag():
    engine, organization, facility, _product, lot = _setup()
    with pytest.raises(ValueError, match="METRC tag mismatch"):
        CoaDocumentService(engine).ingest_for_lot(
            organization.id,
            facility.id,
            lot.id,
            payload=_coa_pdf(OTHER_PACKAGE_ID),
            filename="wrong-coa.pdf",
            content_type="application/pdf",
            actor="qa",
        )


def test_library_coa_auto_matches_package_and_populates_label_results():
    engine, organization, facility, _product, lot = _setup()
    document = CoaDocumentService(engine).ingest_library(
        organization.id,
        facility.id,
        payload=_coa_pdf(),
        filename="copper-kush-coa.pdf",
        content_type="application/pdf",
        actor="qa",
    )
    assert document["package_id"] == PACKAGE_ID
    assert document["verification_state"] == "tag_extracted"
    assert document["lot_id"] == lot.id

    source = LabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)
    assert source["coa"]["available"] is True
    assert source["coa"]["lookup_key"] == PACKAGE_ID
    assert source["coa"]["fallback_allowed"] is False
    assert source["label"]["package_size"] == "3.5 g"
    assert source["label"]["net_contents"] == "NET WT. .12345 OZ"
    assert source["label"]["laboratory"] == "Example Cannabis Lab"
    assert source["label"]["test_date"] == "2026-08-30"
    assert source["label"]["expiration_date"] == "2027-08-30"
    assert source["label"]["total_thc"] == "28.4%"
    assert source["label"]["total_cannabinoids"] == "31.9%"
    assert source["label"]["total_terpenes"] == "2.4%"
    assert source["label"]["qr_value"] == PACKAGE_ID
    assert source["qr"]["value"] == PACKAGE_ID
    assert "<svg" in source["qr"]["svg"]
    assert "THCA 31.2%" in source["label"]["potency"]
    assert {row["key"] for row in source["coa"]["results"]} >= {"thca", "delta_9_thc", "cbga", "beta_myrcene", "limonene"}
    with Session(engine) as session:
        quality = session.get(LotQualityEvidence, lot.id)
        assert quality is not None
        assert quality.coa_document_id == document["id"]
        assert quality.total_thc_percent == 28.4
        assert quality.total_cannabinoids_percent == 31.9


def test_tagless_fallback_requires_explicit_confirmation_before_label_uses_it():
    engine, organization, facility, _product, lot = _setup()
    service = CoaDocumentService(engine)
    document = service.ingest_for_lot(
        organization.id,
        facility.id,
        lot.id,
        payload=_coa_pdf(include_tag=False),
        filename="tagless-coa.pdf",
        content_type="application/pdf",
        actor="qa",
    )
    assert document["status"] == "needs_confirmation"
    assert document["verification_state"] == "operator_confirmation_required"
    pending = LabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)
    assert pending["coa"]["available"] is False
    assert pending["coa"]["needs_confirmation"] is True
    assert pending["label"]["total_thc"] == ""

    service.confirm_for_lot(organization.id, facility.id, lot.id, document["id"], actor="qa")
    confirmed = LabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)
    assert confirmed["coa"]["available"] is True
    assert confirmed["coa"]["verification_state"] == "operator_confirmed"
    assert confirmed["label"]["total_thc"] == "28.4%"
    assert confirmed["label"]["expiration_date"] == "2027-08-30"
