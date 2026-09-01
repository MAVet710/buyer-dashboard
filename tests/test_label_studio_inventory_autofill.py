import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.inventory_quality.models import LotQualityEvidence
from modules.product_master.models import ProductMasterProfile


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _seed(engine):
    with Session(engine) as session, session.begin():
        org = Organization(name="Vertical Cannabis", slug="vertical-cannabis")
        other_org = Organization(name="Other Operator", slug="other-operator")
        session.add_all([org, other_org]); session.flush()
        facility = Facility(
            organization_id=org.id,
            name="New Bedford Manufacturing",
            code="NB-MFG",
            license_number="MP281999",
            license_type="Marijuana Product Manufacturer",
            production_enabled=True,
        )
        other_facility = Facility(
            organization_id=org.id,
            name="Separate Facility",
            code="SEP",
            license_number="MC282000",
            license_type="Marijuana Cultivator",
        )
        session.add_all([facility, other_facility]); session.flush()
        product = Product(
            organization_id=org.id,
            sku="CK-FLR-35",
            name="Copper Kush Flower 3.5g",
            item_type="finished_good",
            base_unit="unit",
            upc="012345678905",
        )
        session.add(product); session.flush()
        session.add(ProductMasterProfile(
            organization_id=org.id,
            product_id=product.id,
            brand="Cowboy Kush",
            category="Flower",
            strain="Copper Kush",
            manufacturer="Vertical Cannabis",
            product_format="Whole flower",
        ))
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="BATCH-CK-0901",
            compliance_package_id="1A4000000000000000012345",
            location_code="FINISHED-GOODS",
            notes=json.dumps({
                "net_contents": "3.5 g",
                "ingredients": "Cannabis flower",
                "allergens": "None declared",
                "warning_text": "Approved internal warning text",
                "laboratory": "Example Cannabis Lab",
                "analysis_date": "2026-08-30",
                "total_thc_percent": 28.4,
                "batch_name": "BATCH-CK-0901",
                "package_date": "2026-09-01",
            }),
        )
        session.add(lot); session.flush()
        session.add(InventoryTransaction(
            organization_id=org.id,
            facility_id=facility.id,
            lot_id=lot.id,
            transaction_type="receipt",
            quantity_delta=24,
            unit="unit",
            actor="tester",
        ))
        session.add(LotQualityEvidence(
            lot_id=lot.id,
            organization_id=org.id,
            facility_id=facility.id,
            lab_testing_state="Passed",
            coa_reference="COA-CK-0901",
            coa_url="https://example.invalid/coa/ck-0901",
            thca_percent=31.2,
            total_thc_percent=28.4,
            total_terpenes_percent=2.1,
            evidence_source="verified_test_fixture",
            actor="tester",
        ))

        hidden_lot = InventoryLot(
            organization_id=org.id,
            facility_id=other_facility.id,
            product_id=product.id,
            lot_code="OTHER-FACILITY-BATCH",
            compliance_package_id="1A4000000000000000099999",
            location_code="VAULT",
        )
        session.add(hidden_lot); session.flush()
        session.add(InventoryTransaction(
            organization_id=org.id,
            facility_id=other_facility.id,
            lot_id=hidden_lot.id,
            transaction_type="receipt",
            quantity_delta=100,
            unit="unit",
            actor="tester",
        ))

        empty_lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="EMPTY-BATCH",
            compliance_package_id="1A4000000000000000088888",
            location_code="FINISHED-GOODS",
        )
        session.add(empty_lot); session.flush()
        session.add_all([
            InventoryTransaction(
                organization_id=org.id, facility_id=facility.id, lot_id=empty_lot.id,
                transaction_type="receipt", quantity_delta=10, unit="unit", actor="tester",
            ),
            InventoryTransaction(
                organization_id=org.id, facility_id=facility.id, lot_id=empty_lot.id,
                transaction_type="shipment", quantity_delta=-10, unit="unit", actor="tester",
            ),
        ])
        return org.id, facility.id, lot.id


def test_inventory_label_source_autofills_authoritative_batch_data():
    engine = _engine()
    org_id, facility_id, lot_id = _seed(engine)

    sources = LabelInventoryService(engine).list_sources(org_id, facility_id)

    assert [row["lot_id"] for row in sources] == [lot_id]
    source = sources[0]
    assert source["on_hand"] == pytest.approx(24)
    assert source["source_summary"] == {
        "facility": "New Bedford Manufacturing",
        "license_number": "MP281999",
        "license_type": "Marijuana Product Manufacturer",
        "qa_source": "verified_test_fixture",
        "coa_source": "",
        "coa_verification": "missing",
    }
    assert source["label"]["product_name"] == "Copper Kush Flower 3.5g"
    assert source["label"]["brand"] == "Cowboy Kush"
    assert source["label"]["strain"] == "Copper Kush"
    assert source["label"]["package_size"] == "3.5 g"
    assert source["label"]["net_contents"] == "NET WT. .12345 OZ"
    assert source["label"]["license_number"] == "MP281999"
    assert source["label"]["package_id"] == "1A4000000000000000012345"
    assert source["label"]["batch_number"] == "BATCH-CK-0901"
    assert source["label"]["potency"] == "THCA 31.2% · Total THC 28.4% · Total terpenes 2.1%"
    assert source["label"]["lab_testing_state"] == "Passed"
    assert source["label"]["coa_reference"] == "COA-CK-0901"
    assert source["label"]["coa_url"] == "https://example.invalid/coa/ck-0901"
    assert source["label"]["warning_text"] == "Approved internal warning text"
    assert "NET WT. .12345 OZ" in source["raw_text"]
    assert "Approved internal warning text" in source["raw_text"]


def test_inventory_label_source_does_not_invent_net_contents_or_traceability_id():
    engine = _engine()
    with Session(engine) as session, session.begin():
        org = Organization(name="No Guess Org", slug="no-guess-org")
        session.add(org); session.flush()
        facility = Facility(organization_id=org.id, name="Facility", code="FAC", license_number="LIC-1")
        product = Product(
            organization_id=org.id,
            sku="BULK-1000",
            name="Bulk Flower 1000g",
            item_type="cannabis",
            base_unit="g",
        )
        session.add_all([facility, product]); session.flush()
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="LOT-1000",
            external_inventory_id="VENDOR-REFERENCE-123",
            location_code="BULK",
            notes=json.dumps({"inventory_quantity": 1000}),
        )
        session.add(lot); session.flush()
        session.add(InventoryTransaction(
            organization_id=org.id,
            facility_id=facility.id,
            lot_id=lot.id,
            transaction_type="receipt",
            quantity_delta=1000,
            unit="g",
            actor="tester",
        ))
        org_id, facility_id = org.id, facility.id

    source = LabelInventoryService(engine).list_sources(org_id, facility_id)[0]
    assert source["on_hand"] == pytest.approx(1000)
    assert source["label"]["net_contents"] == ""
    assert source["label"]["package_id"] == ""
    assert source["label"]["batch_number"] == "LOT-1000"


def test_get_source_rejects_batch_outside_active_facility():
    engine = _engine()
    org_id, facility_id, _ = _seed(engine)
    with pytest.raises(ValueError, match="active facility"):
        LabelInventoryService(engine).get_source(org_id, facility_id, "not-in-this-facility")
