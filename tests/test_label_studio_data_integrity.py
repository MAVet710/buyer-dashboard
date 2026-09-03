from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO

from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio_fast import FastLabelInventoryService
from backend.app.services.label_studio_integrity import (
    normalize_testing_label_source,
    testing_source_mismatches as source_mismatches,
)
from modules.coman import ComanRepository
from modules.coman.models import Base, Facility
from modules.inventory_quality import CoaDocumentService, LotQualityEvidence
from modules.inventory_quality.coa import parse_coa_pdf


PACKAGE = "1A4000000000000000008123"


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _coa_pdf(package_id: str = PACKAGE) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    lines = [
        "Product Name: Integrity Kush Flower",
        "Batch Number: IK-2026-08",
        "Testing Laboratory: Integrity Cannabis Lab",
        "Lab License Number: IL281234",
        "Lab ID: COA-INTEGRITY-1",
        "Date Collected: 08/28/2026",
        "Date Received: 08/29/2026",
        "Date Tested: 08/30/2026",
        "Analysis Date: 08/31/2026",
        "Overall Status: Pass",
        f"METRC Source Package ID: {package_id}",
        "THCA | 30.10 %",
        "Delta-9 THC | 0.45 %",
        "Total THC | 26.84 %",
        "Total CBD | 0.12 %",
        "Total Cannabinoids | 31.20 %",
        "Total Terpenes | 2.75 %",
    ]
    y = 760
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 22
    pdf.save()
    return buffer.getvalue()


def test_coa_parser_keeps_tested_collected_and_received_dates_distinct() -> None:
    parsed = parse_coa_pdf(_coa_pdf())

    assert parsed["date_collected"].date().isoformat() == "2026-08-28"
    assert parsed["date_received"].date().isoformat() == "2026-08-29"
    # Date Tested is the testing-label date; the later Analysis Date must not win.
    assert parsed["date_tested"].date().isoformat() == "2026-08-30"


def test_selected_source_uses_verified_coa_test_date_despite_conflicting_metadata() -> None:
    engine = _engine()
    repo = ComanRepository(engine)
    organization = repo.create_organization("Label Integrity Org")
    facility = repo.create_facility(organization.id, "Integrity Manufacturing", "INT-MFG")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.license_number = "MP281234"
        row.license_type = "Marijuana Product Manufacturer"
        row.production_enabled = True

    product = repo.create_product(
        organization.id,
        sku="IK-FLR",
        name="Integrity Kush Flower",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=8,
        actor="qa",
    )
    lot = repo.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="IK-FG-001",
        actor="qa",
        opening_quantity=24,
        unit="unit",
        location_code="FINISHED-GOODS",
        compliance_package_id=PACKAGE,
    )
    # These dates deliberately conflict with the certificate. Neither may
    # replace the verified laboratory Date Tested in Label Studio.
    with Session(engine) as session, session.begin():
        row = session.get(type(lot), lot.id)
        assert row is not None
        row.notes = json.dumps(
            {
                "analysis_date": "2026-09-02",
                "test_date": "2026-09-03",
                "package_date": "2026-08-31",
                "serial_number": "INT-001",
            }
        )

    document = CoaDocumentService(engine).ingest_library(
        organization.id,
        facility.id,
        payload=_coa_pdf(),
        filename="integrity-kush-coa.pdf",
        content_type="application/pdf",
        actor="qa",
    )

    source = FastLabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)

    assert source["coa"]["document_id"] == document["id"]
    assert source["coa"]["available"] is True
    assert source["coa"]["date_tested"] == "2026-08-30"
    assert source["label"]["test_date"] == "2026-08-30"
    assert source["label"]["expiration_date"] == "2027-08-30"
    assert source["label"]["laboratory"] == "Integrity Cannabis Lab"
    assert source["label"]["lab_license_number"] == "IL281234"
    assert source["label"]["coa_reference"] == "COA-INTEGRITY-1"
    assert source["label"]["lab_testing_state"] == "Passed"
    assert source["label"]["total_thc"] == "26.84%"
    assert source["label"]["total_cbd"] == "0.12%"
    assert source["label"]["total_cannabinoids"] == "31.2%"
    assert source["label"]["total_terpenes"] == "2.75%"
    assert "THCA 30.1%" in source["label"]["potency"]

    assert source["package_id"] == PACKAGE
    assert source["label"]["package_id"] == PACKAGE
    assert source["label"]["qr_value"] == PACKAGE
    assert source["qr"]["value"] == PACKAGE
    assert source["barcode"]["value"] == PACKAGE
    assert source["label"]["batch_number"] == "IK-2026-08"
    assert source["label"]["serial_number"] == "INT-001"
    assert source["label"]["package_date"] == "2026-08-31"
    assert source_mismatches(source) == []


def test_quality_verification_timestamp_is_never_exposed_as_laboratory_test_date() -> None:
    engine = _engine()
    repo = ComanRepository(engine)
    organization = repo.create_organization("No COA Date Org")
    facility = repo.create_facility(organization.id, "No COA Manufacturing", "NOCOA")
    product = repo.create_product(
        organization.id,
        sku="NOCOA-FLR",
        name="No COA Flower",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=5,
        actor="qa",
    )
    lot = repo.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="NOCOA-001",
        actor="qa",
        opening_quantity=10,
        unit="unit",
        location_code="FINISHED-GOODS",
        compliance_package_id="1A4000000000000000008999",
    )
    with Session(engine) as session, session.begin():
        lot_row = session.get(type(lot), lot.id)
        assert lot_row is not None
        lot_row.notes = json.dumps(
            {
                "analysis_date": "2026-08-20",
                "test_date": "2026-08-21",
                "laboratory": "Old Metadata Lab",
                "lab_license_number": "OLD-LAB",
                "total_thc_percent": 99.9,
            }
        )
        session.add(
            LotQualityEvidence(
                lot_id=lot.id,
                organization_id=organization.id,
                facility_id=facility.id,
                lab_testing_state="Passed",
                coa_reference="legacy-quality-record",
                total_thc_percent=88.8,
                evidence_source="manual",
                actor="qa",
                verified_at=datetime(2026, 9, 2, 15, 30, tzinfo=timezone.utc),
            )
        )

    source = FastLabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)

    assert source["coa"]["available"] is False
    assert source["coa"]["date_tested"] == ""
    # No unverified QA/metadata value can masquerade as verified lab evidence.
    for field in (
        "test_date",
        "lab_testing_state",
        "laboratory",
        "lab_license_number",
        "coa_reference",
        "potency",
        "total_thc",
        "total_cbd",
        "total_cannabinoids",
        "total_terpenes",
    ):
        assert source["label"][field] == ""
    assert source_mismatches(source) == []


def test_integrity_boundary_clears_stale_coa_owned_values_when_coa_omits_them() -> None:
    source = {
        "package_id": PACKAGE,
        "label": {
            "package_id": "WRONG",
            "qr_value": "WRONG",
            "test_date": "2026-09-03",
            "lab_testing_state": "Passed",
            "laboratory": "Old Lab",
            "lab_license_number": "OLD-LICENSE",
            "coa_reference": "OLD-COA",
            "potency": "THCA 99%",
            "total_thc": "99%",
            "total_cbd": "99%",
            "total_cannabinoids": "99%",
            "total_terpenes": "99%",
        },
        "coa": {
            "available": True,
            "date_tested": "2026-08-30",
            "overall_status": "pass",
            "lab_name": "",
            "lab_license_number": "",
            "lab_id": "",
            "filename": "authoritative-coa.pdf",
            "total_thc": None,
            "total_cbd": None,
            "total_cannabinoids": None,
            "total_terpenes": None,
            "results": [],
        },
        "qr": {"value": "WRONG", "svg": "<svg/>"},
        "barcode": {"value": "WRONG", "format": "Code128", "svg": "<svg/>"},
    }

    normalized = normalize_testing_label_source(source)

    assert normalized["label"]["test_date"] == "2026-08-30"
    assert normalized["label"]["lab_testing_state"] == "Passed"
    assert normalized["label"]["laboratory"] == ""
    assert normalized["label"]["lab_license_number"] == ""
    assert normalized["label"]["coa_reference"] == "authoritative-coa.pdf"
    assert normalized["label"]["potency"] == ""
    assert normalized["label"]["total_thc"] == ""
    assert normalized["label"]["total_cbd"] == ""
    assert normalized["label"]["total_cannabinoids"] == ""
    assert normalized["label"]["total_terpenes"] == ""
    assert normalized["label"]["package_id"] == PACKAGE
    assert normalized["label"]["qr_value"] == PACKAGE
    assert normalized["qr"]["value"] == PACKAGE
    assert normalized["barcode"]["value"] == PACKAGE
    assert source_mismatches(normalized) == []
