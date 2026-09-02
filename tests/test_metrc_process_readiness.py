from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.cultivation.service import CultivationService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.regulatory.metrc_process_compliance import MetrcProcessComplianceService, MetrcStrictTransferService
from modules.regulatory.metrc_process_models import (
    CultivationAdditiveApplication,
    CultivationHarvestPlantWeight,
    CultivationManicureBatch,
    CultivationRegulatoryIdentity,
    CultivationTestSample,
    CultivationWasteRecord,
    MetrcTagInventory,
)
from modules.regulatory.write_registry import get_metrc_write_contract


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-metrc", name="Metrc Readiness", slug="metrc-readiness"))
        session.add_all([
            Facility(
                id="facility-grow",
                organization_id="org-metrc",
                name="Grow",
                code="GROW",
                license_number="LIC-GROW",
                license_type="Cultivator",
                cultivation_enabled=True,
                production_enabled=True,
                retail_enabled=False,
            ),
            Facility(
                id="facility-retail",
                organization_id="org-metrc",
                name="Retail",
                code="RETAIL",
                license_number="LIC-RETAIL",
                license_type="Retailer",
                cultivation_enabled=False,
                production_enabled=False,
                retail_enabled=True,
            ),
        ])
        product = Product(
            id="product-flower",
            organization_id="org-metrc",
            sku="FLOWER",
            name="Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=2.0,
        )
        session.add(product)
        session.flush()
        lot = InventoryLot(
            id="source-package",
            organization_id="org-metrc",
            facility_id="facility-grow",
            product_id=product.id,
            lot_code="SOURCE-PKG",
            compliance_package_id="1A40-PACKAGE-001",
            external_inventory_id="1A40-PACKAGE-001",
            barcode_value="1A40-PACKAGE-001",
            location_code="VAULT",
            status="released",
        )
        session.add(lot)
        session.flush()
        session.add(InventoryTransaction(
            organization_id="org-metrc",
            facility_id="facility-grow",
            lot_id=lot.id,
            transaction_type="receipt",
            quantity_delta=100.0,
            unit="g",
            actor="seed",
        ))
    return engine


def _balance(engine, lot_id: str) -> float:
    with Session(engine) as session:
        return float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot_id)) or 0.0)


def _sync(service: MetrcProcessComplianceService, *, plants: list[str], packages: list[str]) -> None:
    service.sync_available_tags(
        "org-metrc", "facility-grow",
        jurisdiction_code="MA", license_number="LIC-GROW", environment="sandbox",
        plant_records=[{"label": label} for label in plants],
        package_records=[{"label": label} for label in packages],
    )


def _open_harvest(engine, service: MetrcProcessComplianceService, *, group_code: str, harvest_code: str, plant_tags: list[str]):
    cultivation = CultivationService(engine)
    group = service.create_immature_group(
        "org-metrc", "facility-grow",
        group_code=group_code, group_type="clone_batch", strain_name="GMO", quantity=len(plant_tags),
        origin_type="source_package", origin_reference="1A40-PACKAGE-001",
        source_lot_id="source-package", actor="grower", room_code="NURSERY",
    )
    group = service.assign_vegetative_tags(
        "org-metrc", "facility-grow", group["id"], environment="sandbox", actor="grower",
        provider_confirmed=True, tag_labels=plant_tags,
    )
    for row in group["plants"]:
        cultivation.transition("org-metrc", "facility-grow", row["id"], phase="flowering", room_code="FLOWER-A", actor="grower")
    harvest = cultivation.create_harvest(
        "org-metrc", "facility-grow", harvest_code=harvest_code,
        plant_ids=[row["id"] for row in group["plants"]], actor="grower",
    )
    return group, harvest


def test_immature_origin_and_metrc_tag_identity_are_separate_until_vegetative():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)

    with pytest.raises(ValueError, match="origin reference"):
        service.create_immature_group(
            "org-metrc", "facility-grow",
            group_code="CLONES-1", group_type="clone_batch", strain_name="GMO", quantity=2,
            origin_type="state_authorized", origin_reference="", actor="grower",
        )

    group = service.create_immature_group(
        "org-metrc", "facility-grow",
        group_code="CLONES-1", group_type="clone_batch", strain_name="GMO", quantity=2,
        origin_type="source_package", origin_reference="1A40-PACKAGE-001",
        source_lot_id="source-package", actor="grower", room_code="NURSERY",
    )
    assert {row["phase"] for row in group["plants"]} == {"clone"}
    assert all(row["metrc_plant_tag"] is None for row in group["plants"])
    assert all(row["plant_tag"].startswith("DL-CLONES-1-") for row in group["plants"])

    _sync(service, plants=["1A40-PLANT-001", "1A40-PLANT-002", "1A40-PLANT-003"], packages=["1A40-TEST-001"])
    with pytest.raises(ValueError, match="Confirm the Metrc"):
        service.assign_vegetative_tags(
            "org-metrc", "facility-grow", group["id"], environment="sandbox",
            actor="grower", provider_confirmed=False,
        )

    veg = service.assign_vegetative_tags(
        "org-metrc", "facility-grow", group["id"], environment="sandbox",
        actor="grower", provider_confirmed=True,
    )
    assert {row["phase"] for row in veg["plants"]} == {"vegetative"}
    assert {row["metrc_plant_tag"] for row in veg["plants"]} == {"1A40-PLANT-001", "1A40-PLANT-002"}

    first = veg["plants"][0]
    replaced = service.replace_plant_tag(
        "org-metrc", "facility-grow", first["id"], environment="sandbox",
        new_tag_label="1A40-PLANT-003", actor="grower", provider_confirmed=True,
    )
    assert replaced["previous_metrc_plant_tag"] in {"1A40-PLANT-001", "1A40-PLANT-002"}
    assert replaced["metrc_plant_tag"] == "1A40-PLANT-003"

    with Session(engine) as session:
        identities = list(session.scalars(select(CultivationRegulatoryIdentity)))
        assert len(identities) == 2
        used = list(session.scalars(select(MetrcTagInventory).where(MetrcTagInventory.status == "used")))
        assert len(used) == 3


def test_tag_sync_marks_provider_missing_available_tag_unavailable():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    _sync(service, plants=["PLANT-A", "PLANT-B"], packages=["PKG-A"])
    _sync(service, plants=["PLANT-B"], packages=[])
    with Session(engine) as session:
        plant_a = session.scalar(select(MetrcTagInventory).where(MetrcTagInventory.label == "PLANT-A"))
        plant_b = session.scalar(select(MetrcTagInventory).where(MetrcTagInventory.label == "PLANT-B"))
        pkg_a = session.scalar(select(MetrcTagInventory).where(MetrcTagInventory.label == "PKG-A"))
        assert plant_a.status == "unavailable"
        assert plant_b.status == "available"
        assert pkg_a.status == "unavailable"


def test_harvest_requires_every_plant_wet_weight_and_structured_process_records():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    _sync(service, plants=["P-1", "P-2", "P-3"], packages=["TEST-1"])
    group, harvest = _open_harvest(engine, service, group_code="SEEDS-1", harvest_code="HARV-1", plant_tags=["P-1", "P-2"])

    with pytest.raises(ValueError, match="exactly every plant"):
        service.record_harvest_wet_weights(
            "org-metrc", "facility-grow", harvest["id"],
            plant_weights=[{"plant_id": group["plants"][0]["id"], "wet_weight_g": 400}],
            actor="grower", provider_confirmed=True,
        )
    result = service.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest["id"],
        plant_weights=[
            {"plant_id": group["plants"][0]["id"], "wet_weight_g": 400},
            {"plant_id": group["plants"][1]["id"], "wet_weight_g": 350},
        ],
        actor="grower", provider_confirmed=True,
    )
    assert result["wet_weight_g"] == pytest.approx(750)

    waste = service.record_waste(
        "org-metrc", "facility-grow", actor="grower", provider_confirmed=True,
        target_type="harvest", target_id=harvest["id"], method="Grind and mix",
        material_mixed="non-cannabis waste", weight=25, unit="g", reason="Stem/leaf waste",
        waste_date=date.today(), location="DRY-A", measurement_basis="wet", notes="",
    )
    assert waste["weight"] == 25

    second = service.create_immature_group(
        "org-metrc", "facility-grow",
        group_code="CLONES-2", group_type="clone_batch", strain_name="GMO", quantity=1,
        origin_type="source_package", origin_reference="1A40-PACKAGE-001",
        source_lot_id="source-package", actor="grower",
    )
    second = service.assign_vegetative_tags(
        "org-metrc", "facility-grow", second["id"], environment="sandbox", actor="grower", provider_confirmed=True,
        tag_labels=["P-3"],
    )
    manicure = service.create_manicure_batch(
        "org-metrc", "facility-grow", batch_code="MAN-1", source_phase="vegetative", location="VEG-A",
        manicure_date=date.today(), plant_weights=[{"plant_id": second["plants"][0]["id"], "weight_g": 12.5}],
        notes="Usable material removed before harvest", actor="grower", provider_confirmed=True,
    )
    assert manicure["total_weight_g"] == pytest.approx(12.5)

    additive = service.record_additive(
        "org-metrc", "facility-grow", actor="grower", target_type="plant",
        target_id=second["plants"][0]["id"], product_name="Nutrient A", epa_number="",
        supplier="Vendor", amount=10, unit="mL", active_ingredients="", application_date=date.today(), notes="",
    )
    assert additive["product_name"] == "Nutrient A"

    sample = service.create_test_sample(
        "org-metrc", "facility-grow", environment="sandbox", source_type="harvest", source_id=harvest["id"],
        package_tag="TEST-1", quantity=5, unit="g", actor="qa", provider_confirmed=False,
    )
    assert sample["status"] == "planned"
    confirmed = service.confirm_test_sample(
        "org-metrc", "facility-grow", sample["id"], provider_reference="METRC-SAMPLE-1", actor="qa",
    )
    assert confirmed["status"] == "provider_confirmed"

    with Session(engine) as session:
        assert session.scalar(select(func.count(CultivationHarvestPlantWeight.id))) == 2
        assert session.scalar(select(func.count(CultivationWasteRecord.id))) == 1
        assert session.scalar(select(func.count(CultivationManicureBatch.id))) == 1
        assert session.scalar(select(func.count(CultivationAdditiveApplication.id))) == 1
        sample_row = session.scalar(select(CultivationTestSample))
        assert sample_row.environment == "sandbox"


def test_harvest_finish_classifies_only_remaining_weight_as_moisture_loss():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    _sync(service, plants=["H-P1", "H-P2"], packages=[])
    group, harvest = _open_harvest(engine, service, group_code="H-GROUP", harvest_code="H-CLOSE", plant_tags=["H-P1", "H-P2"])
    service.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest["id"],
        plant_weights=[
            {"plant_id": group["plants"][0]["id"], "wet_weight_g": 400},
            {"plant_id": group["plants"][1]["id"], "wet_weight_g": 350},
        ], actor="grower", provider_confirmed=True,
    )
    allocation = GuardedHarvestAllocationService(engine)
    preview = allocation.preview_harvest_allocation(
        organization_id="org-metrc", facility_id="facility-grow", harvest_id=harvest["id"],
        outputs=[{
            "product_id": "product-flower", "lot_code": "HARV-PKG-1", "quantity": 500,
            "unit": "g", "purpose": "finished_flower", "measurement_basis": "wet",
            "status": "quarantine", "location_code": "DRY-A", "compliance_package_id": "METRC-HARV-PKG-1",
        }],
        losses=[],
    )
    allocation.commit_harvest_allocation(
        organization_id="org-metrc", facility_id="facility-grow", harvest_id=harvest["id"],
        outputs=preview["outputs"], losses=[], preview_key=preview["preview_key"], actor="grower",
    )
    service.record_waste(
        "org-metrc", "facility-grow", actor="grower", provider_confirmed=True,
        target_type="harvest", target_id=harvest["id"], method="Grind and mix", material_mixed="waste",
        weight=25, unit="g", reason="Stem/leaf", waste_date=date.today(), location="DRY-A",
        measurement_basis="wet", notes="",
    )
    before = service.harvest_closeout_preview("org-metrc", "facility-grow", harvest["id"])
    assert before["output_g"] == pytest.approx(500)
    assert before["reported_loss_or_waste_g"] == pytest.approx(25)
    assert before["remaining_for_moisture_loss_g"] == pytest.approx(225)
    with pytest.raises(ValueError, match="all actual harvest waste"):
        service.finish_harvest(
            "org-metrc", "facility-grow", harvest["id"], actor="grower",
            provider_confirmed=True, all_waste_reported=False,
        )
    closed = service.finish_harvest(
        "org-metrc", "facility-grow", harvest["id"], actor="grower",
        provider_confirmed=True, all_waste_reported=True,
    )
    assert closed["status"] == "completed"
    assert closed["existing_moisture_loss_g"] == pytest.approx(225)
    assert closed["remaining_for_moisture_loss_g"] == pytest.approx(0)


def test_harvest_discontinue_restores_plants_only_before_waste_or_output():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    _sync(service, plants=["D-P1", "D-P2"], packages=[])
    group, harvest = _open_harvest(engine, service, group_code="D-GROUP", harvest_code="D-HARV", plant_tags=["D-P1"])
    service.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest["id"],
        plant_weights=[{"plant_id": group["plants"][0]["id"], "wet_weight_g": 100}], actor="grower", provider_confirmed=True,
    )
    result = service.discontinue_harvest(
        "org-metrc", "facility-grow", harvest["id"], actor="grower",
        provider_confirmed=True, reason="Created in error",
    )
    assert result["status"] == "cancelled"
    with Session(engine) as session:
        plant = session.get(__import__("modules.cultivation.models", fromlist=["CultivationPlant"]).CultivationPlant, group["plants"][0]["id"])
        assert plant.phase == "flowering"
        assert plant.retired_at is None

    group2, harvest2 = _open_harvest(engine, service, group_code="D-GROUP-2", harvest_code="D-HARV-2", plant_tags=["D-P2"])
    service.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest2["id"],
        plant_weights=[{"plant_id": group2["plants"][0]["id"], "wet_weight_g": 100}], actor="grower", provider_confirmed=True,
    )
    service.record_waste(
        "org-metrc", "facility-grow", actor="grower", provider_confirmed=True,
        target_type="harvest", target_id=harvest2["id"], method="Grind", material_mixed="waste", weight=5,
        unit="g", reason="Waste", waste_date=date.today(), location="DRY-A", measurement_basis="wet", notes="",
    )
    with pytest.raises(ValueError, match="after waste"):
        service.discontinue_harvest(
            "org-metrc", "facility-grow", harvest2["id"], actor="grower",
            provider_confirmed=True, reason="Too late",
        )


def test_add_forgotten_plant_uses_existing_harvest_identity_and_individual_weight():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    _sync(service, plants=["A-P1", "A-P2"], packages=[])
    cultivation = CultivationService(engine)
    group = service.create_immature_group(
        "org-metrc", "facility-grow", group_code="A-GROUP", group_type="clone_batch", strain_name="GMO", quantity=2,
        origin_type="source_package", origin_reference="1A40-PACKAGE-001", source_lot_id="source-package", actor="grower",
    )
    group = service.assign_vegetative_tags(
        "org-metrc", "facility-grow", group["id"], environment="sandbox", actor="grower", provider_confirmed=True,
        tag_labels=["A-P1", "A-P2"],
    )
    for row in group["plants"]:
        cultivation.transition("org-metrc", "facility-grow", row["id"], phase="flowering", room_code="FLOWER-A", actor="grower")
    harvest = cultivation.create_harvest(
        "org-metrc", "facility-grow", harvest_code="A-HARV", plant_ids=[group["plants"][0]["id"]], actor="grower",
    )
    service.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest["id"],
        plant_weights=[{"plant_id": group["plants"][0]["id"], "wet_weight_g": 100}], actor="grower", provider_confirmed=True,
    )
    with Session(engine) as session:
        row = session.get(__import__("modules.operational_moats.models", fromlist=["CultivationHarvest"]).CultivationHarvest, harvest["id"])
        harvest_date = row.harvested_at.date()
    added = service.add_plants_to_harvest(
        "org-metrc", "facility-grow", harvest["id"], harvest_date=harvest_date,
        plant_weights=[{"plant_id": group["plants"][1]["id"], "wet_weight_g": 90}], actor="grower", provider_confirmed=True,
    )
    assert added["added_plant_count"] == 1
    with Session(engine) as session:
        count = session.scalar(select(func.count(CultivationHarvestPlantWeight.id)).where(CultivationHarvestPlantWeight.harvest_id == harvest["id"]))
        assert count == 2


def test_destroy_plant_records_structured_waste_before_retirement():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    _sync(service, plants=["X-P1"], packages=[])
    group = service.create_immature_group(
        "org-metrc", "facility-grow", group_code="X-GROUP", group_type="clone_batch", strain_name="GMO", quantity=1,
        origin_type="source_package", origin_reference="1A40-PACKAGE-001", source_lot_id="source-package", actor="grower",
    )
    group = service.assign_vegetative_tags(
        "org-metrc", "facility-grow", group["id"], environment="sandbox", actor="grower", provider_confirmed=True,
        tag_labels=["X-P1"],
    )
    result = service.destroy_plant(
        "org-metrc", "facility-grow", group["plants"][0]["id"], method="Grind and mix", material_mixed="soil",
        weight=15, unit="g", reason="Cull", waste_date=date.today(), location="VEG-A", notes="", actor="grower",
        provider_confirmed=True,
    )
    assert result["phase"] == "destroyed"
    with Session(engine) as session:
        waste = session.scalar(select(CultivationWasteRecord).where(CultivationWasteRecord.target_type == "plant"))
        assert waste.weight == pytest.approx(15)
        assert waste.method == "Grind and mix"


def test_package_discontinue_is_separate_from_finish_and_fails_closed_after_activity():
    engine = _engine()
    service = MetrcProcessComplianceService(engine)
    external = service.package_discontinue_preflight("org-metrc", "facility-grow", "source-package")
    assert external["eligible_local"] is False
    assert any("source lineage" in blocker for blocker in external["blockers"])

    _sync(service, plants=["Z-P1"], packages=[])
    group, harvest = _open_harvest(engine, service, group_code="Z-GROUP", harvest_code="Z-HARV", plant_tags=["Z-P1"])
    service.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest["id"],
        plant_weights=[{"plant_id": group["plants"][0]["id"], "wet_weight_g": 100}], actor="grower", provider_confirmed=True,
    )
    allocation = GuardedHarvestAllocationService(engine)
    preview = allocation.preview_harvest_allocation(
        organization_id="org-metrc", facility_id="facility-grow", harvest_id=harvest["id"],
        outputs=[{
            "product_id": "product-flower", "lot_code": "ERROR-PKG", "quantity": 50, "unit": "g",
            "purpose": "finished_flower", "measurement_basis": "wet", "status": "quarantine",
            "location_code": "DRY", "compliance_package_id": "ERROR-METRC-PKG",
        }], losses=[],
    )
    committed = allocation.commit_harvest_allocation(
        organization_id="org-metrc", facility_id="facility-grow", harvest_id=harvest["id"],
        outputs=preview["outputs"], losses=[], preview_key=preview["preview_key"], actor="grower",
    )
    error_lot = committed["output_lot_ids"][0]
    eligible = service.package_discontinue_preflight("org-metrc", "facility-grow", error_lot)
    assert eligible["eligible_local"] is True
    assert eligible["provider_operation"] == "package_discontinue"
    assert eligible["provider_dispatch"].startswith("locked")

    with Session(engine) as session, session.begin():
        session.add(InventoryTransaction(
            organization_id="org-metrc", facility_id="facility-grow", lot_id=error_lot,
            transaction_type="adjustment", quantity_delta=-1, unit="g", actor="operator",
        ))
    blocked = service.package_discontinue_preflight("org-metrc", "facility-grow", error_lot)
    assert blocked["eligible_local"] is False
    assert any("activity after creation" in blocker for blocker in blocked["blockers"])


def test_strict_metrc_transfer_blocks_partial_and_rejected_return_restores_source():
    engine = _engine()
    service = MetrcStrictTransferService(engine)

    with pytest.raises(ValueError, match="complete packages"):
        service.dispatch_whole_packages(
            "org-metrc", "facility-grow", destination_facility_id="facility-retail",
            manifest_reference="MAN-PARTIAL", lines=[{"source_lot_id": "source-package", "quantity": 40}], actor="shipper",
        )
    assert _balance(engine, "source-package") == pytest.approx(100)

    transfer = service.dispatch_whole_packages(
        "org-metrc", "facility-grow", destination_facility_id="facility-retail",
        manifest_reference="MAN-001", provider_transfer_id="METRC-XFER-1",
        lines=[{"source_lot_id": "source-package", "quantity": 100}], actor="shipper",
    )
    line = transfer["lines"][0]
    assert transfer["metrc_control"]["provider_status"] == "departed"
    assert transfer["metrc_control"]["departure_confirmed_at"]
    assert _balance(engine, "source-package") == pytest.approx(0)
    with pytest.raises(ValueError, match="cannot be cancelled after actual departure"):
        service.assert_cancellable("org-metrc", transfer["id"])

    rejected = service.reject_package(
        "org-metrc", "facility-retail", transfer["id"], line["id"], actor="receiver",
        reason="Package rejected", return_manifest_reference="RETURN-001",
    )
    assert rejected["metrc_rejections"][0]["status"] == "returning"
    with pytest.raises(ValueError, match="rejected"):
        service.receive_whole_package(
            "org-metrc", "facility-retail", transfer["id"], line["id"], operation="retail", actor="receiver"
        )

    returned = service.receive_rejected_return(
        "org-metrc", "facility-grow", transfer["id"], line["id"], actor="shipper", state_return_confirmed=True,
    )
    assert returned["metrc_control"]["provider_status"] == "returned"
    assert _balance(engine, "source-package") == pytest.approx(100)


def test_strict_metrc_transfer_receive_keeps_manifested_package_identity():
    engine = _engine()
    service = MetrcStrictTransferService(engine)
    transfer = service.dispatch_whole_packages(
        "org-metrc", "facility-grow", destination_facility_id="facility-retail",
        manifest_reference="MAN-RECEIVE", lines=[{"source_lot_id": "source-package", "quantity": 100}], actor="shipper",
    )
    line = transfer["lines"][0]
    received = service.receive_whole_package(
        "org-metrc", "facility-retail", transfer["id"], line["id"], operation="retail", actor="receiver",
        location="RECEIVING",
    )
    received_line = received["lines"][0]
    with Session(engine) as session:
        lot = session.get(InventoryLot, received_line["destination_lot_id"])
        assert lot.compliance_package_id == "1A40-PACKAGE-001"
        destination_balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot.id)) or 0.0)
        assert destination_balance == pytest.approx(100)


def test_new_metrc_write_contracts_are_registered_but_sandbox_locked():
    for operation in (
        "package_discontinue",
        "plant_tag_replace",
        "plant_strain_update",
        "plant_harvest",
        "plant_manicure",
        "plant_additive",
        "plant_batch_growthphase",
        "harvest_test_package",
        "harvest_waste",
        "harvest_finish",
        "harvest_unfinish",
        "harvest_restore_plants",
    ):
        contract = get_metrc_write_contract(operation)
        assert contract is not None
        assert contract.dispatch_enabled is False
        assert "MA" in contract.jurisdictions
        assert "sandbox" in contract.environments
