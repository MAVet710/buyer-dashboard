from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services.label_studio import LabelInventoryService
from modules.coman import ComanRepository
from modules.coman.models import Base, Facility
from modules.coman.vertical_demo_ma_coas import seed_dev_ma_flower_reference_coa
from modules.inventory_quality import LotQualityEvidence


def _setup(name: str, *, facility_code: str = "SANDBOX"):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization(name)
    facility = coman.create_facility(organization.id, "Sandbox Facility", facility_code)
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.license_number = "DEV-SANDBOX-VERTICAL"
        row.production_enabled = True
    product = coman.create_product(
        organization.id,
        sku="RUNTZ-BULK",
        name="Runtz OG Bulk Flower",
        item_type="cannabis",
        base_unit="g",
        unit_cost=2,
        actor="test",
    )
    lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=product.id,
        lot_code="DEVV-RUNTZ-FLOWER",
        actor="test",
        opening_quantity=2220,
        unit="g",
        location_code="BULK-FLOWER",
        compliance_package_id="DEV-HARV-RUNTZ-FLOWER",
    )
    document = seed_dev_ma_flower_reference_coa(
        engine,
        organization.id,
        facility.id,
        lot.id,
        strain="Runtz OG",
        actor="test",
    )
    return engine, organization, facility, lot, document


def test_dev_sandbox_label_source_reads_real_external_reference_coa_without_bypass():
    engine, organization, facility, lot, document = _setup("DEV Sandbox")

    source = LabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)

    assert source["package_id"] == "DEV-HARV-RUNTZ-FLOWER"
    assert source["qr"]["value"] == "DEV-HARV-RUNTZ-FLOWER"
    assert source["coa"]["available"] is True
    assert source["coa"]["needs_confirmation"] is False
    assert source["coa"]["fallback_allowed"] is False
    assert source["coa"]["document_id"] == document.id
    assert source["coa"]["verification_state"] == "external_reference"
    assert source["coa"]["metrc_source_id"]
    assert source["coa"]["metrc_source_id"] != source["package_id"]
    assert source["coa"]["overall_status"].casefold() == "pass"
    assert source["coa"]["date_tested"]
    assert source["coa"]["lab_name"]
    assert source["coa"]["lab_license_number"]
    assert source["coa"]["results"]
    assert source["label"]["laboratory"] == source["coa"]["lab_name"]
    assert source["label"]["lab_license_number"] == source["coa"]["lab_license_number"]
    assert source["label"]["test_date"] == source["coa"]["date_tested"]
    assert source["label"]["total_thc"]
    assert source["label"]["total_cannabinoids"]
    assert source["label"]["total_terpenes"]
    assert "THCA" in source["label"]["potency"]

    with Session(engine) as session:
        quality = session.get(LotQualityEvidence, lot.id)
        assert quality is not None
        assert quality.evidence_source == "coa:dev_ma_external_reference"
        assert quality.lab_testing_state == "Passed"


def test_external_reference_coa_is_not_promoted_outside_exact_dev_tenant():
    engine, organization, facility, lot, document = _setup("Not DEV Sandbox")

    source = LabelInventoryService(engine).get_source(organization.id, facility.id, lot.id)

    assert document.verification_state == "external_reference"
    assert source["coa"]["available"] is False
    assert source["coa"]["document_id"] == ""
    assert source["label"]["package_id"] == "DEV-HARV-RUNTZ-FLOWER"
    assert source["qr"]["value"] == "DEV-HARV-RUNTZ-FLOWER"
