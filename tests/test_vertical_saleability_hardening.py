from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import Base, Facility, InventoryLot, Product
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.extraction import ExtractionRepository
from modules.inventory_quality import LotQualityEvidence, LotQualityService
from modules.material_lineage.service import MaterialLineageService
from modules.package_studio import (
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
    PackageStudioService,
)
from modules.product_master import ProductMasterRepository, ProductPackagingProfile, ProductPackagingService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _profile(master: ProductMasterRepository, organization_id: str, product_id: str, *, category: str, product_format: str) -> None:
    master.update_profile(
        organization_id,
        product_id,
        actor="hardening-test",
        brand="Cowboy Kush",
        category=category,
        product_format=product_format,
        strain="Gastro Pop",
        manufacturer="Cowboy Kush Vertical",
        retail_enabled=True,
        production_enabled=True,
    )


def test_extraction_quality_lineage_cogs_and_saleability_flow_end_to_end():
    engine = _engine()
    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    extraction = ExtractionRepository(engine)
    studio = PackageStudioService(engine)

    organization = coman.create_organization("Vertical Hardening")
    facility = coman.create_facility(organization.id, "Vertical Facility", "VH")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.production_enabled = True
        row.cultivation_enabled = True
        row.retail_enabled = True
        row.commercial_enabled = True
        row.license_number = "TEST-LICENSE"

    trim_product = coman.create_product(
        organization.id,
        sku="GP-TRIM",
        name="Gastro Pop Trim",
        item_type="cannabis",
        base_unit="g",
        unit_cost=1.0,
        actor="hardening-test",
    )
    _profile(master, organization.id, trim_product.id, category="Trim", product_format="Bulk Trim")
    trim_lot = coman.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=trim_product.id,
        lot_code="GP-TRIM-001",
        opening_quantity=100,
        unit="g",
        compliance_package_id="METRC-GP-TRIM-001",
        actor="hardening-test",
    )
    with Session(engine) as session, session.begin():
        LotQualityService.set_evidence(
            session,
            lot_id=trim_lot.id,
            lab_testing_state="Passed",
            coa_reference="COA-GP-TRIM",
            thca_percent=18.2,
            tac_percent=21.4,
            total_terpenes_percent=1.7,
            evidence_source="lab_import",
            actor="hardening-test",
        )

    bulk_product = coman.create_product(
        organization.id,
        sku="GP-BADDER-BULK",
        name="Gastro Pop Cured Badder Bulk",
        item_type="cannabis",
        base_unit="g",
        unit_cost=0,
        actor="hardening-test",
    )
    _profile(master, organization.id, bulk_product.id, category="Bulk Extract", product_format="Cured Badder")
    retail_product = coman.create_product(
        organization.id,
        sku="GP-BADDER-1G",
        name="Gastro Pop Cured Badder 1g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=0,
        retail_price=35,
        upc="860000000001",
        actor="hardening-test",
    )
    _profile(master, organization.id, retail_product.id, category="Concentrates", product_format="Cured Badder 1g")
    with Session(engine) as session, session.begin():
        ProductPackagingService.upsert(
            session,
            organization_id=organization.id,
            product_id=retail_product.id,
            net_content=1.0,
            net_content_unit="g",
            units_per_package=1,
            sellable_unit="each",
            case_pack=24,
        )

    run = extraction.create_run(
        organization_id=organization.id,
        facility_id=facility.id,
        batch_number="EXT-GP-001",
        method="BHO",
        workflow_key="bho_cured",
        product_family="Cured Badder",
        strain="Gastro Pop",
        actor="hardening-test",
    )
    run_input = extraction.reserve_input(
        organization_id=organization.id,
        facility_id=facility.id,
        run_id=run.id,
        lot_id=trim_lot.id,
        quantity=50,
        unit="g",
        actor="hardening-test",
    )
    extraction.consume_input(
        organization_id=organization.id,
        facility_id=facility.id,
        run_input_id=run_input.id,
        quantity=50,
        actor="hardening-test",
    )
    extraction.add_cost_event(
        organization_id=organization.id,
        facility_id=facility.id,
        run_id=run.id,
        category="labor",
        amount_usd=25,
        quantity=1,
        unit="hour",
        actor="hardening-test",
    )
    output = extraction.create_output(
        organization_id=organization.id,
        facility_id=facility.id,
        run_id=run.id,
        product_id=bulk_product.id,
        lot_code="GP-BADDER-BULK-001",
        quantity=10,
        unit="g",
        compliance_package_id="METRC-GP-BADDER-BULK-001",
        actor="hardening-test",
    )
    extraction.record_qa_event(
        organization_id=organization.id,
        facility_id=facility.id,
        run_id=run.id,
        output_id=output.id,
        event_type="coa_attached",
        result="passed",
        coa_reference="COA-GP-BADDER",
        actor="hardening-test",
    )
    extraction.record_qa_event(
        organization_id=organization.id,
        facility_id=facility.id,
        run_id=run.id,
        event_type="release",
        result="passed",
        actor="hardening-test",
    )

    assert coman.inventory_balance(organization.id, trim_lot.id) == pytest.approx(50)
    with Session(engine) as session:
        evidence = session.get(LotQualityEvidence, output.lot_id)
        assert evidence is not None
        assert evidence.lab_testing_state == "Passed"
        assert evidence.coa_reference == "COA-GP-BADDER"
        bulk = session.get(Product, bulk_product.id)
        assert bulk is not None
        assert bulk.unit_cost == pytest.approx(7.5)

    packaged = studio.commit(
        PackageStudioPlan(
            action_type="build_run",
            inputs=(PackageStudioInputPlan(lot_id=output.lot_id, quantity=10, unit="g"),),
            outputs=(
                PackageStudioOutputPlan(
                    product_id=retail_product.id,
                    lot_code="GP-BADDER-1G-LOT",
                    inventory_quantity=10,
                    inventory_unit="unit",
                    source_equivalent_quantity=10,
                    source_equivalent_unit="g",
                    compliance_package_id="METRC-GP-BADDER-1G-LOT",
                    purpose="standard",
                    location_code="FINISHED-GOODS",
                ),
            ),
            source_unit="g",
            run_number="PKG-GP-BADDER-001",
            reason="Pack released extraction output",
        ),
        organization_id=organization.id,
        facility_id=facility.id,
        actor="hardening-test",
    )
    final_lot_id = packaged.output_lot_ids[0]

    with Session(engine) as session:
        evidence = session.get(LotQualityEvidence, final_lot_id)
        assert evidence is not None
        assert evidence.lab_testing_state == "Passed"
        assert evidence.coa_reference == "COA-GP-BADDER"
        packaging = session.get(ProductPackagingProfile, retail_product.id)
        assert packaging is not None
        assert packaging.net_content == pytest.approx(1)
        assert packaging.net_content_unit == "g"
        assert packaging.case_pack == pytest.approx(24)
        retail = session.get(Product, retail_product.id)
        assert retail is not None
        assert retail.unit_cost == pytest.approx(7.5)

    wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(organization.id, facility.id)
    sellable_ids = {row["lot_id"] for row in wholesale["items"]}
    assert final_lot_id in sellable_ids

    graph = MaterialLineageService(engine).lot_graph(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=final_lot_id,
    )
    node_keys = {row["key"] for row in graph["nodes"]}
    transform_types = {row.get("transformation_type") for row in graph["nodes"] if row["type"] == "transformation"}
    assert f"lot:{trim_lot.id}" in node_keys
    assert "extraction_run" in transform_types
    assert "package_studio:build_run" in transform_types

    blocked_run = extraction.create_run(
        organization_id=organization.id,
        facility_id=facility.id,
        batch_number="EXT-GP-BLOCKED",
        method="BHO",
        workflow_key="bho_cured",
        product_family="Cured Badder",
        strain="Gastro Pop",
        actor="hardening-test",
    )
    with pytest.raises(ValueError, match="not eligible"):
        extraction.reserve_input(
            organization_id=organization.id,
            facility_id=facility.id,
            run_id=blocked_run.id,
            lot_id=final_lot_id,
            quantity=1,
            unit="unit",
            actor="hardening-test",
        )
