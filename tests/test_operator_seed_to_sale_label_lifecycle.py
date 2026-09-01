from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.label_studio import LabelInventoryService
from modules.coman import ComanRepository
from modules.coman.models import Base, Facility
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.cultivation.service import CultivationService
from modules.inventory_quality import LotQualityService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.package_studio import PackageStudioInputPlan, PackageStudioOutputPlan, PackageStudioPlan, PackageStudioService
from modules.product_master import ProductMasterRepository, ProductPackagingService


def test_operator_can_move_seedling_to_saleable_labeled_finished_inventory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    master = ProductMasterRepository(engine)
    cultivation = CultivationService(engine)
    harvest_allocator = GuardedHarvestAllocationService(engine)
    studio = PackageStudioService(engine)

    organization = coman.create_organization("Operator Lifecycle")
    facility = coman.create_facility(organization.id, "Vertical Facility", "VERT")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.cultivation_enabled = True
        row.production_enabled = True
        row.retail_enabled = True
        row.commercial_enabled = True
        row.license_number = "VERTICAL-LICENSE-001"
        row.license_type = "cultivation+manufacturing+wholesale"

    bulk = coman.create_product(
        organization.id,
        sku="SEED-BULK-FLOWER",
        name="Operator Kush Bulk Flower",
        item_type="cannabis",
        base_unit="g",
        unit_cost=2,
        actor="operator-alpha",
    )
    master.update_profile(
        organization.id,
        bulk.id,
        actor="operator-alpha",
        brand="Operator Kush",
        category="Bulk Flower",
        subcategory="Bulk Flower",
        strain="Operator Kush",
        manufacturer="Vertical Facility",
        product_format="Bulk Flower",
        retail_enabled=False,
        production_enabled=True,
    )

    plant = cultivation.create_plant(
        organization.id,
        facility.id,
        plant_tag="SEEDLING-0001",
        strain_name="Operator Kush",
        phase="seedling",
        room_code="SEEDLING-A",
        actor="operator-alpha",
    )
    plant = cultivation.transition(
        organization.id,
        facility.id,
        plant.id,
        phase="vegetative",
        room_code="VEG-A",
        reason="Seedling established",
        actor="operator-alpha",
    )
    plant = cultivation.transition(
        organization.id,
        facility.id,
        plant.id,
        phase="flowering",
        room_code="FLOWER-A",
        reason="Ready for flower",
        actor="operator-alpha",
    )
    assert plant.phase == "flowering"

    harvest = cultivation.create_harvest(
        organization.id,
        facility.id,
        harvest_code="HARVEST-0001",
        plant_ids=[plant.id],
        actor="operator-alpha",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="active",
        wet_weight=1000,
        unit="g",
        actor="operator-alpha",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="drying",
        dry_weight=250,
        unit="g",
        actor="operator-alpha",
    )
    outputs = [{
        "product_id": bulk.id,
        "lot_code": "HARVEST-0001-FLOWER",
        "quantity": 250,
        "unit": "g",
        "purpose": "finished_flower",
        "measurement_basis": "dry",
        "status": "available",
        "location_code": "BULK-FLOWER",
        "compliance_package_id": "HARVEST-PKG-0001",
    }]
    preview = harvest_allocator.preview_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=[],
    )
    assert preview["reconciliation"]["dry"]["remaining"] == 0
    committed = harvest_allocator.commit_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=[],
        preview_key=preview["preview_key"],
        actor="operator-alpha",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="completed",
        actor="operator-alpha",
    )
    bulk_lot_id = committed["output_lot_ids"][0]
    with Session(engine) as session, session.begin():
        LotQualityService.set_evidence(
            session,
            lot_id=bulk_lot_id,
            lab_testing_state="Passed",
            coa_reference="COA-OPERATOR-0001",
            thca_percent=28.5,
            tac_percent=31.2,
            total_terpenes_percent=2.4,
            evidence_source="operator_lifecycle_lab",
            actor="operator-alpha",
        )

    finished = coman.create_product(
        organization.id,
        sku="OP-KUSH-35",
        name="Operator Kush Flower 3.5g",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=0,
        retail_price=35,
        upc="850000000001",
        actor="operator-alpha",
    )
    master.update_profile(
        organization.id,
        finished.id,
        actor="operator-alpha",
        brand="Operator Kush",
        category="Flower",
        subcategory="Flower Jar 3.5g",
        strain="Operator Kush",
        manufacturer="Vertical Facility",
        product_format="Flower Jar 3.5g",
        retail_enabled=True,
        production_enabled=True,
    )
    with Session(engine) as session, session.begin():
        ProductPackagingService.upsert(
            session,
            organization_id=organization.id,
            product_id=finished.id,
            net_content=3.5,
            net_content_unit="g",
            case_pack=24,
        )

    packaged = studio.commit(
        PackageStudioPlan(
            action_type="build_run",
            inputs=(PackageStudioInputPlan(lot_id=bulk_lot_id, quantity=35, unit="g"),),
            outputs=(PackageStudioOutputPlan(
                product_id=finished.id,
                lot_code="OP-KUSH-35-LOT",
                inventory_quantity=10,
                inventory_unit="unit",
                source_equivalent_quantity=35,
                source_equivalent_unit="g",
                compliance_package_id="PKG-OP-KUSH-35",
                purpose="standard",
                location_code="FINISHED-GOODS",
            ),),
            source_unit="g",
            run_number="PKG-RUN-OP-0001",
            reason="Operator seed-to-sale acceptance",
        ),
        organization_id=organization.id,
        facility_id=facility.id,
        actor="operator-alpha",
    )
    final_lot_id = packaged.output_lot_ids[0]

    label = LabelInventoryService(engine).get_source(organization.id, facility.id, final_lot_id)
    assert label["label"]["product_name"] == "Operator Kush Flower 3.5g"
    assert label["label"]["brand"] == "Operator Kush"
    assert label["label"]["strain"] == "Operator Kush"
    assert label["label"]["package_size"] == "3.5 g"
    assert label["label"]["net_contents"] == "NET WT. .12345 OZ"
    assert label["label"]["license_number"] == "VERTICAL-LICENSE-001"
    assert label["label"]["package_id"] == "PKG-OP-KUSH-35"
    assert label["qr"]["value"] == "PKG-OP-KUSH-35"
    assert "<svg" in label["qr"]["svg"]
    assert label["label"]["lab_testing_state"] == "Passed"
    assert label["label"]["coa_reference"] == "COA-OPERATOR-0001"
    assert "THCA 28.5%" in label["label"]["potency"]

    wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(organization.id, facility.id)
    assert final_lot_id in {row["lot_id"] for row in wholesale["items"]}

    events = cultivation.events(organization.id, facility.id, plant.id)
    assert [(event.event_type, event.to_value) for event in events if event.event_type == "phase_changed"] == [
        ("phase_changed", "vegetative"),
        ("phase_changed", "flowering"),
    ]
    harvested = [event for event in events if event.event_type == "harvested"]
    assert len(harvested) == 1
    assert harvested[0].from_value == "flowering"
    assert harvested[0].to_value == "HARVEST-0001"
    assert cultivation.harvest_detail(organization.id, facility.id, harvest["id"])["plants"][0]["phase"] == "harvested"
