from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import zlib

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product, utc_now
from modules.inventory_quality.models import CoaAnalyteResult, CoaDocument
from modules.label_studio_workflow import LabelProductionWorkflowService
from modules.product_master.models import ProductMasterProfile
from modules.product_master.packaging import ProductPackagingProfile


SOURCE_TAG = "1A4000000000000000097001"
FINISHED_TAG = "1A4000000000000000097999"


def _engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _seed():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Functional Output Cannabis", slug="functional-output-cannabis")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Functional Output Manufacturing",
            code="FO-MFG",
            license_number="MP281234",
            license_type="Marijuana Product Manufacturer",
            production_enabled=True,
        )
        source_product = Product(
            organization_id=organization.id,
            sku="FO-GMO-BULK",
            name="GMO Bulk Flower",
            item_type="cannabis",
            base_unit="g",
            active=True,
        )
        finished_product = Product(
            organization_id=organization.id,
            sku="FO-GMO-PR-28",
            name="GMO 28-Count Pre-Roll Multipack",
            item_type="finished_good",
            base_unit="unit",
            active=True,
        )
        session.add_all([facility, source_product, finished_product])
        session.flush()
        session.add_all([
            ProductMasterProfile(
                organization_id=organization.id,
                product_id=source_product.id,
                brand="Functional Output Reserve",
                category="Flower",
                strain="GMO",
                manufacturer="Functional Output Manufacturing",
                product_format="Flower",
                production_enabled=True,
            ),
            ProductMasterProfile(
                organization_id=organization.id,
                product_id=finished_product.id,
                brand="Functional Output Reserve",
                category="Pre-Rolls",
                subcategory="Multipack",
                strain="GMO",
                manufacturer="Functional Output Manufacturing",
                product_format="Pre-Rolls",
                production_enabled=True,
            ),
            ProductPackagingProfile(
                organization_id=organization.id,
                product_id=finished_product.id,
                net_content=28,
                net_content_unit="g",
                units_per_package=28,
                sellable_unit="each",
                case_pack=0,
                warning_text="Required package warning",
                label_layout="compact_single",
                label_width_in=3.5,
                label_height_in=2.1,
                label_source_count=1,
            ),
        ])
        source_lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=source_product.id,
            lot_code="FO-GMO-BULK-01",
            compliance_package_id=SOURCE_TAG,
            location_code="BULK",
            status="available",
            notes=json.dumps({
                "harvest_date": "2026-08-01",
                "cultivated_by": "Source Grower LLC",
                "cultivator_license": "MC281111",
                "cultivator_contact": "New Bedford, MA",
                "batch_number": "GMO-H-01",
                "package_date": "2026-08-31",
            }),
        )
        session.add(source_lot)
        session.flush()
        session.add(InventoryTransaction(
            organization_id=organization.id,
            facility_id=facility.id,
            lot_id=source_lot.id,
            transaction_type="receipt",
            quantity_delta=4000,
            unit="g",
            actor="functional-output-seed",
        ))

        payload = json.dumps({"fixture": "functional-output-label-studio", "package_id": SOURCE_TAG}, sort_keys=True).encode()
        coa = CoaDocument(
            organization_id=organization.id,
            facility_id=facility.id,
            lot_id=source_lot.id,
            package_id=SOURCE_TAG,
            source="functional_output_fixture",
            status="parsed",
            verification_state="matched",
            filename="functional-output-gmo-coa.json",
            content_type="application/json",
            fingerprint=sha256(payload).hexdigest(),
            payload_compressed=zlib.compress(payload),
            payload_size=len(payload),
            parser_name="functional-output-fixture",
            parser_version="1",
            product_name="GMO Bulk Flower",
            product_type="Flower",
            strain_name="GMO",
            batch_number="GMO-H-01",
            lab_name="Functional Output Lab",
            lab_license_number="IL281234",
            lab_id="FO-GMO-COA-1",
            metrc_source_id=SOURCE_TAG,
            metrc_lab_id="1A4000000000000000097998",
            metrc_ids_json=json.dumps([SOURCE_TAG, "1A4000000000000000097998"]),
            date_tested=datetime(2026, 8, 30, tzinfo=timezone.utc),
            overall_status="pass",
            total_thc_percent=29.4,
            total_cbd_percent=0.1,
            total_cannabinoids_percent=31.1,
            total_terpenes_percent=3.2,
            raw_payload_json=json.dumps({"fixture": "functional-output-label-studio"}),
            imported_by="functional-output-seed",
            verified_at=utc_now(),
        )
        session.add(coa)
        session.flush()
        # Terpenes are intentionally not potency-sorted. The rendered label layer
        # must select its top terpene facts by value rather than trusting source order.
        results = [
            ("cannabinoids", "thca", "THCA", 33.0, "33.0", "%"),
            ("cannabinoids", "delta_9_thc", "Delta-9 THC", 0.45, "0.45", "%"),
            ("terpenes", "linalool", "Linalool", 0.30, "0.30", "%"),
            ("terpenes", "limonene", "Limonene", 1.20, "1.20", "%"),
            ("terpenes", "alpha_humulene", "Alpha-Humulene", 0.10, "0.10", "%"),
            ("terpenes", "beta_caryophyllene", "Beta-Caryophyllene", 0.90, "0.90", "%"),
            ("terpenes", "beta_myrcene", "Beta-Myrcene", 0.70, "0.70", "%"),
        ]
        for order, (analysis, key, name, value, value_text, units) in enumerate(results):
            session.add(CoaAnalyteResult(
                coa_document_id=coa.id,
                organization_id=organization.id,
                facility_id=facility.id,
                analysis=analysis,
                analyte_key=key,
                name=name,
                value=value,
                value_text=value_text,
                units=units,
                status="Pass",
                sort_order=order,
            ))

        return engine, organization.id, facility.id, source_lot.id, finished_product.id


def test_label_studio_real_services_produce_exact_finished_label_facts_and_traceability():
    engine, organization_id, facility_id, source_lot_id, finished_product_id = _seed()

    source = LabelInventoryService(engine).get_source(organization_id, facility_id, source_lot_id)
    label = source["label"]
    assert source["package_id"] == SOURCE_TAG
    assert source["coa"]["available"] is True
    assert source["coa"]["overall_status"] == "pass"
    assert source["coa"]["lab_name"] == "Functional Output Lab"
    assert source["coa"]["date_tested"] == "2026-08-30"
    assert label["total_thc"] == "29.4%"
    assert label["total_cbd"] == "0.1%"
    assert label["total_cannabinoids"] == "31.1%"
    assert label["total_terpenes"] == "3.2%"
    assert label["test_date"] == "2026-08-30"
    assert label["expiration_date"] == "2027-08-30"
    assert source["qr"]["value"] == SOURCE_TAG
    assert source["barcode"]["value"] == SOURCE_TAG

    workflow = LabelProductionWorkflowService(engine)
    run = workflow.create_run(
        organization_id,
        facility_id,
        source_lot_id=source_lot_id,
        product_id=finished_product_id,
        quantity=24,
        actor="packaging-operator",
    )
    assert run["status"] == "validated"
    assert run["quantity"] == 24
    assert run["expected_material_quantity"] == 0
    assert run["snapshot"]["label"]["product_name"] == "GMO 28-Count Pre-Roll Multipack"
    assert run["snapshot"]["label"]["brand"] == "Functional Output Reserve"
    assert run["snapshot"]["label"]["strain"] == "GMO"
    assert run["snapshot"]["label"]["package_size"] == "28 g"
    assert run["snapshot"]["label"]["net_contents"] == "NET WT. .98767 OZ"
    assert run["snapshot"]["label"]["package_composition"] == "28 x 1g Pre-Rolls"
    assert run["snapshot"]["label"]["total_thc"] == "29.4%"
    assert run["snapshot"]["label"]["total_cbd"] == "0.1%"
    assert run["snapshot"]["label"]["total_cannabinoids"] == "31.1%"
    assert run["snapshot"]["label"]["total_terpenes"] == "3.2%"
    assert run["snapshot"]["source"]["label"]["expiration_date"] == "2027-08-30"
    assert run["snapshot"]["source"]["package_id"] == SOURCE_TAG
    assert run["snapshot"]["source"]["coa"]["document_id"] == source["coa"]["document_id"]
    assert run["snapshot"]["print_layout"] == {
        "layout": "compact_single",
        "width_in": 3.5,
        "height_in": 2.1,
        "source_count": 1,
    }

    tagged = workflow.assign_tag(
        organization_id,
        facility_id,
        run["id"],
        FINISHED_TAG,
        "packaging-operator",
    )
    assert tagged["status"] == "tagged"
    assert tagged["metrc_package_tag"] == FINISHED_TAG
    assert tagged["snapshot"]["label"]["package_id"] == FINISHED_TAG
    assert tagged["traceability"]["qr"]["value"] == FINISHED_TAG
    assert "<svg" in tagged["traceability"]["qr"]["svg"]
    assert tagged["traceability"]["barcode"]["value"] == FINISHED_TAG
    assert tagged["traceability"]["barcode"]["format"] == "Code128"
    assert "<svg" in tagged["traceability"]["barcode"]["svg"]

    printed = workflow.record_print(
        organization_id,
        facility_id,
        run["id"],
        actor="packaging-operator",
        copies=24,
    )
    assert printed["status"] == "printed"
    assert printed["printed_by"] == "packaging-operator"
    printed_event = next(event for event in printed["events"] if event["event_type"] == "printed")
    assert printed_event["details"] == {"copies": 24}
    assert printed["snapshot"]["source"]["lot_id"] == source_lot_id
    assert printed["snapshot"]["source"]["package_id"] == SOURCE_TAG
    assert printed["snapshot"]["label"]["package_id"] == FINISHED_TAG
