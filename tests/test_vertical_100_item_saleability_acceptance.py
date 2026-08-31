from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import Base, Facility, InventoryLot, Product
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.cultivation.service import CultivationService
from modules.extraction import ExtractionRepository
from modules.inventory_quality import LotQualityEvidence, LotQualityService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.material_lineage.service import MaterialLineageService
from modules.package_studio import PackageStudioInputPlan, PackageStudioOutputPlan, PackageStudioPlan, PackageStudioService
from modules.product_master import ProductMasterRepository, ProductPackagingProfile, ProductPackagingService


STRAINS = (
    "Gastro Pop",
    "GMO",
    "Strawberry Cough",
    "Blue Dream",
    "Wedding Cake",
    "Super Lemon Haze",
    "Gelato 41",
    "Motorbreath",
    "Permanent Marker",
    "Animal Face",
)

FLOWER_FORMATS = (
    ("Flower Jar 1g", 1.0, 10, 24),
    ("Flower Jar 3.5g", 3.5, 10, 24),
    ("Flower Pouch 7g", 7.0, 5, 12),
    ("Flower Pouch 14g", 14.0, 2, 8),
    ("Flower Pouch 28g", 28.0, 1, 4),
    ("Smalls Pouch 3.5g", 3.5, 10, 24),
    ("Ground Flower Pouch 7g", 7.0, 5, 12),
)

EXTRACT_FORMATS = (
    ("bho_cured", "BHO", "Cured Badder 1g"),
    ("ethanol_crude", "Ethanol", "Distillate 1g"),
    ("dry_sift", "Dry Sift", "Dry Sift 1g"),
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _profile(master: ProductMasterRepository, organization_id: str, product_id: str, *, strain: str, category: str, product_format: str) -> None:
    master.update_profile(
        organization_id,
        product_id,
        actor="vertical-100",
        brand="Cowboy Kush",
        category=category,
        subcategory=product_format,
        strain=strain,
        manufacturer="Cowboy Kush Vertical",
        product_format=product_format,
        description=f"{strain} {product_format}",
        retail_enabled=True,
        production_enabled=True,
    )


def _quality(engine, lot_id: str, reference: str, *, thca: float, tac: float, terpenes: float) -> None:
    with Session(engine) as session, session.begin():
        LotQualityService.set_evidence(
            session,
            lot_id=lot_id,
            lab_testing_state="Passed",
            coa_reference=reference,
            thca_percent=thca,
            tac_percent=tac,
            total_terpenes_percent=terpenes,
            evidence_source="vertical_100_lab",
            actor="vertical-100",
        )


def _packaging(engine, organization_id: str, product_id: str, *, net_content: float, net_unit: str, case_pack: float) -> None:
    with Session(engine) as session, session.begin():
        ProductPackagingService.upsert(
            session,
            organization_id=organization_id,
            product_id=product_id,
            net_content=net_content,
            net_content_unit=net_unit,
            units_per_package=1,
            sellable_unit="each",
            case_pack=case_pack,
        )


def test_100_finished_items_are_balanced_costed_traceable_and_saleable():
    engine = _engine()
    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    cultivation = CultivationService(engine)
    harvest_allocator = GuardedHarvestAllocationService(engine)
    extraction = ExtractionRepository(engine)
    studio = PackageStudioService(engine)
    lineage = MaterialLineageService(engine)

    organization = coman.create_organization("Cowboy Kush 100 Acceptance")
    facility = coman.create_facility(organization.id, "Vertical Cultivation Manufacturing Wholesale", "V100")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.cultivation_enabled = True
        row.production_enabled = True
        row.retail_enabled = True
        row.commercial_enabled = True
        row.license_number = "VERTICAL-100-LICENSE"
        row.license_type = "cultivation+manufacturing+retail"

    final_lot_ids: list[str] = []
    final_product_ids: list[str] = []
    flower_final_lot_ids: list[str] = []
    extract_final_lot_ids: list[str] = []
    extraction_bulk_lot_ids: list[str] = []

    for strain_index, strain in enumerate(STRAINS, start=1):
        code = f"S{strain_index:02d}"
        flower_source = coman.create_product(
            organization.id,
            sku=f"{code}-BULK-FLOWER",
            name=f"{strain} Bulk Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=2.0,
            actor="vertical-100",
        )
        trim_source = coman.create_product(
            organization.id,
            sku=f"{code}-TRIM",
            name=f"{strain} Trim",
            item_type="cannabis",
            base_unit="g",
            unit_cost=0.75,
            actor="vertical-100",
        )
        _profile(master, organization.id, flower_source.id, strain=strain, category="Bulk Flower", product_format="Bulk Flower")
        _profile(master, organization.id, trim_source.id, strain=strain, category="Trim", product_format="Trim")

        plants = [
            cultivation.create_plant(
                organization.id,
                facility.id,
                plant_tag=f"{code}-P{index:02d}",
                strain_name=strain,
                phase="flowering",
                room_code=f"FLOWER-{strain_index:02d}",
                actor="vertical-100",
            )
            for index in (1, 2)
        ]
        harvest = cultivation.create_harvest(
            organization.id,
            facility.id,
            harvest_code=f"{code}-H-001",
            plant_ids=[plant.id for plant in plants],
            actor="vertical-100",
        )
        cultivation.transition_harvest(
            organization.id,
            facility.id,
            harvest["id"],
            status="active",
            actor="vertical-100",
            wet_weight=4000,
            unit="g",
        )
        cultivation.transition_harvest(
            organization.id,
            facility.id,
            harvest["id"],
            status="drying",
            actor="vertical-100",
            dry_weight=1000,
            unit="g",
        )
        harvest_outputs = [
            {
                "product_id": flower_source.id,
                "lot_code": f"{code}-H-001-FLOWER",
                "quantity": 700,
                "unit": "g",
                "purpose": "finished_flower",
                "measurement_basis": "dry",
                "status": "available",
                "location_code": "BULK-FLOWER-VAULT",
                "compliance_package_id": f"HARV-{code}-FLOWER",
            },
            {
                "product_id": trim_source.id,
                "lot_code": f"{code}-H-001-TRIM",
                "quantity": 300,
                "unit": "g",
                "purpose": "trim",
                "measurement_basis": "dry",
                "status": "available",
                "location_code": "EXTRACTION-STAGING",
                "compliance_package_id": f"HARV-{code}-TRIM",
            },
        ]
        preview = harvest_allocator.preview_harvest_allocation(
            organization_id=organization.id,
            facility_id=facility.id,
            harvest_id=harvest["id"],
            outputs=harvest_outputs,
            losses=[],
        )
        assert preview["reconciliation"]["dry"]["remaining"] == 0
        committed = harvest_allocator.commit_harvest_allocation(
            organization_id=organization.id,
            facility_id=facility.id,
            harvest_id=harvest["id"],
            outputs=harvest_outputs,
            losses=[],
            preview_key=preview["preview_key"],
            actor="vertical-100",
        )
        cultivation.transition_harvest(
            organization.id,
            facility.id,
            harvest["id"],
            status="completed",
            actor="vertical-100",
        )
        flower_lot_id, trim_lot_id = committed["output_lot_ids"]
        _quality(engine, flower_lot_id, f"COA-{code}-FLOWER", thca=26.0, tac=29.0, terpenes=2.1)
        _quality(engine, trim_lot_id, f"COA-{code}-TRIM", thca=18.0, tac=21.0, terpenes=1.5)

        flower_outputs: list[PackageStudioOutputPlan] = []
        flower_source_used = 0.0
        for format_index, (format_name, grams_each, units, case_pack) in enumerate(FLOWER_FORMATS, start=1):
            product = coman.create_product(
                organization.id,
                sku=f"{code}-F{format_index:02d}",
                name=f"{strain} {format_name}",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=0,
                retail_price=round(max(10.0, grams_each * 9.0), 2),
                upc=f"850{strain_index:02d}{format_index:02d}00000",
                actor="vertical-100",
            )
            _profile(master, organization.id, product.id, strain=strain, category="Flower", product_format=format_name)
            _packaging(engine, organization.id, product.id, net_content=grams_each, net_unit="g", case_pack=case_pack)
            final_product_ids.append(product.id)
            source_equivalent = grams_each * units
            flower_source_used += source_equivalent
            flower_outputs.append(
                PackageStudioOutputPlan(
                    product_id=product.id,
                    lot_code=f"{code}-F{format_index:02d}-LOT",
                    inventory_quantity=units,
                    inventory_unit="unit",
                    source_equivalent_quantity=source_equivalent,
                    source_equivalent_unit="g",
                    compliance_package_id=f"PKG-{code}-F{format_index:02d}",
                    purpose="standard",
                    location_code="FINISHED-GOODS",
                )
            )
        flower_pack = studio.commit(
            PackageStudioPlan(
                action_type="multi_build",
                inputs=(PackageStudioInputPlan(lot_id=flower_lot_id, quantity=flower_source_used, unit="g"),),
                outputs=tuple(flower_outputs),
                source_unit="g",
                run_number=f"PKG-{code}-FLOWER",
                reason="Package saleable flower",
            ),
            organization_id=organization.id,
            facility_id=facility.id,
            actor="vertical-100",
        )
        flower_final_lot_ids.extend(flower_pack.output_lot_ids)
        final_lot_ids.extend(flower_pack.output_lot_ids)

        for extract_index, (workflow_key, method, format_name) in enumerate(EXTRACT_FORMATS, start=1):
            bulk = coman.create_product(
                organization.id,
                sku=f"{code}-X{extract_index:02d}-BULK",
                name=f"{strain} {format_name} Bulk",
                item_type="cannabis",
                base_unit="g",
                unit_cost=0,
                actor="vertical-100",
            )
            _profile(master, organization.id, bulk.id, strain=strain, category="Bulk Extract", product_format=format_name)
            finished = coman.create_product(
                organization.id,
                sku=f"{code}-X{extract_index:02d}",
                name=f"{strain} {format_name}",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=0,
                retail_price=35,
                upc=f"860{strain_index:02d}{extract_index:02d}00000",
                actor="vertical-100",
            )
            _profile(master, organization.id, finished.id, strain=strain, category="Concentrates", product_format=format_name)
            _packaging(engine, organization.id, finished.id, net_content=1, net_unit="g", case_pack=12)
            final_product_ids.append(finished.id)

            run = extraction.create_run(
                organization_id=organization.id,
                facility_id=facility.id,
                batch_number=f"EXT-{code}-{extract_index:02d}",
                method=method,
                workflow_key=workflow_key,
                product_family=format_name,
                strain=strain,
                actor="vertical-100",
            )
            run_input = extraction.reserve_input(
                organization_id=organization.id,
                facility_id=facility.id,
                run_id=run.id,
                lot_id=trim_lot_id,
                quantity=50,
                unit="g",
                actor="vertical-100",
            )
            extraction.consume_input(
                organization_id=organization.id,
                facility_id=facility.id,
                run_input_id=run_input.id,
                quantity=50,
                actor="vertical-100",
            )
            extraction.add_cost_event(
                organization_id=organization.id,
                facility_id=facility.id,
                run_id=run.id,
                category="labor",
                amount_usd=25,
                quantity=1,
                unit="hour",
                actor="vertical-100",
            )
            output = extraction.create_output(
                organization_id=organization.id,
                facility_id=facility.id,
                run_id=run.id,
                product_id=bulk.id,
                lot_code=f"EXT-{code}-{extract_index:02d}-BULK",
                quantity=10,
                unit="g",
                compliance_package_id=f"EXT-PKG-{code}-{extract_index:02d}",
                location_code="EXTRACTION-QA",
                actor="vertical-100",
            )
            extraction_bulk_lot_ids.append(output.lot_id)
            extraction.record_qa_event(
                organization_id=organization.id,
                facility_id=facility.id,
                run_id=run.id,
                output_id=output.id,
                event_type="coa_attached",
                result="passed",
                coa_reference=f"COA-EXT-{code}-{extract_index:02d}",
                actor="vertical-100",
            )
            extraction.record_qa_event(
                organization_id=organization.id,
                facility_id=facility.id,
                run_id=run.id,
                event_type="release",
                result="passed",
                actor="vertical-100",
            )
            assert extraction.mass_balance(organization.id, facility.id, run.id)["unaccounted_balance"] == 40
            packaged = studio.commit(
                PackageStudioPlan(
                    action_type="build_run",
                    inputs=(PackageStudioInputPlan(lot_id=output.lot_id, quantity=10, unit="g"),),
                    outputs=(
                        PackageStudioOutputPlan(
                            product_id=finished.id,
                            lot_code=f"{code}-X{extract_index:02d}-LOT",
                            inventory_quantity=10,
                            inventory_unit="unit",
                            source_equivalent_quantity=10,
                            source_equivalent_unit="g",
                            compliance_package_id=f"PKG-{code}-X{extract_index:02d}",
                            purpose="standard",
                            location_code="FINISHED-GOODS",
                        ),
                    ),
                    source_unit="g",
                    run_number=f"PKG-{code}-X{extract_index:02d}",
                    reason="Package released extract",
                ),
                organization_id=organization.id,
                facility_id=facility.id,
                actor="vertical-100",
            )
            extract_final_lot_ids.extend(packaged.output_lot_ids)
            final_lot_ids.extend(packaged.output_lot_ids)

    assert len(final_product_ids) == 100
    assert len(final_lot_ids) == 100
    assert len(flower_final_lot_ids) == 70
    assert len(extract_final_lot_ids) == 30
    assert all(coman.inventory_balance(organization.id, lot_id) > 0 for lot_id in final_lot_ids)

    with Session(engine) as session:
        final_lots = [session.get(InventoryLot, lot_id) for lot_id in final_lot_ids]
        evidences = [session.get(LotQualityEvidence, lot_id) for lot_id in final_lot_ids]
        packaging = [session.get(ProductPackagingProfile, product_id) for product_id in final_product_ids]
        products = [session.get(Product, product_id) for product_id in final_product_ids]
    assert all(lot is not None and lot.status == "available" and lot.compliance_package_id for lot in final_lots)
    assert all(row is not None and row.lab_testing_state == "Passed" and row.coa_reference for row in evidences)
    assert all(row is not None and row.net_content > 0 and row.net_content_unit == "g" for row in packaging)
    assert all(row is not None and row.unit_cost > 0 for row in products)

    wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(organization.id, facility.id)
    final_ids = set(final_lot_ids)
    eligible_final = [row for row in wholesale["items"] if row["lot_id"] in final_ids]
    blocked_final = [row for row in wholesale["blocked_items"] if row["lot_id"] in final_ids]
    assert len(eligible_final) == 100
    assert blocked_final == []

    with_plant_ancestry = 0
    extraction_graphs = 0
    for lot_id in final_lot_ids:
        graph = lineage.lot_graph(organization_id=organization.id, facility_id=facility.id, lot_id=lot_id)
        if any(node["type"] == "plant" for node in graph["nodes"]):
            with_plant_ancestry += 1
        if lot_id in set(extract_final_lot_ids) and any(node.get("transformation_type") == "extraction_run" for node in graph["nodes"]):
            extraction_graphs += 1
    assert with_plant_ancestry == 100
    assert extraction_graphs == 30

    with Session(engine) as session:
        extraction_quality = [session.get(LotQualityEvidence, lot_id) for lot_id in extraction_bulk_lot_ids]
    assert len(extraction_quality) == 30
    assert all(row is not None and row.evidence_source == "extraction_qa" for row in extraction_quality)

    picker_ids = {row["lot_id"] for row in extraction.list_available_lots(organization.id, facility.id)}
    assert final_ids.isdisjoint(picker_ids)
