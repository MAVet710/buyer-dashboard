from io import BytesIO

from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman import ComanRepository
from modules.coman.models import Base, Facility
from modules.inventory_quality import CoaDocumentService, LotQualityEvidence
from modules.package_studio import PackageStudioInputPlan, PackageStudioOutputPlan, PackageStudioPlan, PackageStudioService
from modules.product_master import ProductMasterRepository, ProductPackagingService


TESTED_PACKAGE = "1A4000000000000000007001"
CURRENT_PACKAGE = "1A4000000000000000007002"


def _coa_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    lines = [
        "Product Name: Lineage Kush Bulk Flower",
        "Batch Number: LK-TESTED",
        "Testing Laboratory: Lineage Cannabis Lab",
        "Lab ID: COA-LINEAGE-1",
        "Date Tested: 09/01/2026",
        "Overall Status: Pass",
        f"METRC Source Package ID: {TESTED_PACKAGE}",
        "THCA | 28.50 %",
        "Delta-9 THC | 0.35 %",
        "Beta-Myrcene | 0.72 %",
        "Total THC | 25.35 %",
        "Total Cannabinoids | 29.10 %",
        "Total Terpenes | 2.15 %",
    ]
    y = 760
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 22
    pdf.save()
    return buffer.getvalue()


def test_split_package_keeps_ancestor_coa_but_qr_uses_current_metrc_tag():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    studio = PackageStudioService(engine)

    organization = coman.create_organization("Lineage Label Test")
    facility = coman.create_facility(organization.id, "Vertical Manufacturing", "VERT-MFG")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.production_enabled = True
        row.commercial_enabled = True
        row.license_number = "MP-LINEAGE-1"

    bulk = coman.create_product(
        organization.id,
        sku="LK-BULK",
        name="Lineage Kush Bulk Flower",
        item_type="cannabis",
        base_unit="g",
        unit_cost=2,
        actor="qa",
    )
    finished = coman.create_product(
        organization.id,
        sku="LK-14G",
        name="Lineage Kush Flower 14g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=0,
        retail_price=80,
        actor="qa",
    )
    master.update_profile(
        organization.id,
        finished.id,
        actor="qa",
        brand="Lineage Kush",
        category="Flower",
        subcategory="Flower Pouch 14g",
        strain="Lineage Kush",
        manufacturer="Vertical Manufacturing",
        product_format="Flower Pouch 14g",
        retail_enabled=True,
        production_enabled=True,
    )
    with Session(engine) as session, session.begin():
        ProductPackagingService.upsert(
            session,
            organization_id=organization.id,
            product_id=finished.id,
            net_content=14,
            net_content_unit="g",
            warning_text="Approved packaging warning",
        )

    tested_lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=bulk.id,
        lot_code="LK-TESTED",
        actor="qa",
        opening_quantity=140,
        unit="g",
        location_code="BULK-FLOWER",
        compliance_package_id=TESTED_PACKAGE,
    )
    document = CoaDocumentService(engine).ingest_library(
        organization.id,
        facility.id,
        payload=_coa_pdf(),
        filename="lineage-kush-coa.pdf",
        content_type="application/pdf",
        actor="qa",
    )

    packaged = studio.commit(
        PackageStudioPlan(
            action_type="pack_down",
            inputs=(PackageStudioInputPlan(lot_id=tested_lot.id, quantity=14, unit="g"),),
            outputs=(PackageStudioOutputPlan(
                product_id=finished.id,
                lot_code="LK-14G-CHILD",
                inventory_quantity=1,
                inventory_unit="unit",
                source_equivalent_quantity=14,
                source_equivalent_unit="g",
                compliance_package_id=CURRENT_PACKAGE,
                purpose="standard",
                location_code="FINISHED-GOODS",
            ),),
            source_unit="g",
            run_number="LK-SPLIT-001",
            reason="Split tested flower into a new retail METRC package",
        ),
        organization_id=organization.id,
        facility_id=facility.id,
        actor="operator",
    )
    child_lot_id = packaged.output_lot_ids[0]

    source = LabelInventoryService(engine).get_source(organization.id, facility.id, child_lot_id)
    assert source["package_id"] == CURRENT_PACKAGE
    assert source["label"]["package_id"] == CURRENT_PACKAGE
    assert source["label"]["qr_value"] == CURRENT_PACKAGE
    assert source["qr"]["value"] == CURRENT_PACKAGE
    assert "<svg" in source["qr"]["svg"]
    assert source["coa"]["available"] is True
    assert source["coa"]["fallback_allowed"] is False
    assert source["coa"]["document_id"] == document["id"]
    assert source["coa"]["metrc_source_id"] == TESTED_PACKAGE
    assert source["label"]["test_date"] == "2026-09-01"
    assert source["label"]["expiration_date"] == "2027-09-01"
    assert source["label"]["package_size"] == "14 g"
    assert source["label"]["net_contents"] == "NET WT. .49383 OZ"
    assert source["label"]["warning_text"] == "Approved packaging warning"
    assert "THCA 28.5%" in source["label"]["potency"]

    with Session(engine) as session:
        parent_quality = session.get(LotQualityEvidence, tested_lot.id)
        child_quality = session.get(LotQualityEvidence, child_lot_id)
        assert parent_quality is not None
        assert child_quality is not None
        assert child_quality.coa_document_id == parent_quality.coa_document_id == document["id"]
        assert child_quality.inherited_from_lot_id == tested_lot.id
