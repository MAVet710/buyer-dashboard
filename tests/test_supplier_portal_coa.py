from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database import get_engine
from backend.app.routers.supplier_portal import public_router
from modules.coman.models import Base, Facility, Organization, TradePartner
from modules.inventory_quality.models import CoaDocument
from modules.supplier_portal.coa import CANONICAL_COA_PREFIX
from modules.supplier_portal.service import SupplierPortalService


PACKAGE_ID = "1A4000000000000000007777"


def _coa_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    lines = [
        "Product Name: GMO Bulk Flower",
        "Batch Number: GMO-SUP-0907",
        "Testing Laboratory: Supplier Example Lab",
        "Lab ID: SUP-COA-0907",
        "Date Tested: 09/05/2026",
        "Overall Status: Pass",
        f"METRC Source Package ID: {PACKAGE_ID}",
        "THCA | 30.10 %",
        "Delta-9 THC | 0.80 %",
        "Total THC | 27.20 %",
        "Total CBD | 0.10 %",
        "Total Terpenes | 2.10 %",
    ]
    y = 760
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 22
    pdf.save()
    return buffer.getvalue()


def _setup():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-1", name="Buyer Org", slug="buyer-org"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Buyer Facility", code="BUYER"))
        session.add(TradePartner(id="vendor-1", organization_id="org-1", name="Supplier One", partner_type="vendor"))
    token = SupplierPortalService(engine).issue_supplier_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="vendor-1",
        actor="buyer-1",
    )[2]
    app = FastAPI()
    app.include_router(public_router, prefix="/api/v1")
    app.dependency_overrides[get_engine] = lambda: engine
    return engine, token, TestClient(app)


def _offer(reference: str):
    return {
        "external_reference": "GMO-WHOLESALE",
        "lines": [
            {
                "supplier_sku": "GMO-BULK",
                "product_name": "GMO Bulk Flower",
                "strain": "GMO",
                "form": "flower",
                "available_quantity": 10,
                "availability_unit": "lb",
                "unit_price": 650,
                "price_basis": "lb",
                "minimum_order_quantity": 1,
                "minimum_order_unit": "lb",
                "batch_lot_identifier": "GMO-SUP-0907",
                "coa_reference": reference,
            }
        ],
    }


def test_supplier_pdf_becomes_canonical_coa_and_offer_reference():
    engine, token, client = _setup()
    uploaded = client.post(
        f"/api/v1/commerce-portal/{token}/coas",
        files={"file": ("gmo-coa.pdf", _coa_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["coa_reference"].startswith(CANONICAL_COA_PREFIX)
    assert document["package_id"] == PACKAGE_ID
    assert document["total_thc"] == 27.2

    with Session(engine) as session:
        persisted = session.scalar(select(CoaDocument).where(CoaDocument.id == document["id"]))
        assert persisted is not None
        assert persisted.source == "supplier_portal"
        assert persisted.imported_by.startswith("supplier_portal:")
        assert persisted.metrc_source_id == PACKAGE_ID

    submitted = client.post(
        f"/api/v1/commerce-portal/{token}/offers",
        json=_offer(document["coa_reference"]),
    )
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["lines"][0]["coa_reference"] == document["coa_reference"]


def test_fake_internal_coa_reference_fails_but_external_link_remains_allowed():
    _engine, token, client = _setup()
    fake = client.post(
        f"/api/v1/commerce-portal/{token}/offers",
        json=_offer(f"{CANONICAL_COA_PREFIX}missing-document"),
    )
    assert fake.status_code == 422

    external = client.post(
        f"/api/v1/commerce-portal/{token}/offers",
        json=_offer("https://supplier.example/coa/GMO-SUP-0907.pdf"),
    )
    assert external.status_code == 201, external.text
