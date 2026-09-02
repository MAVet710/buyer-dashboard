from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.cultivation.service import CultivationService
from modules.regulatory.metrc_process_models import (
    CultivationAdditiveApplication,
    CultivationHarvestPlantWeight,
    CultivationManicureBatch,
    CultivationRegulatoryIdentity,
    CultivationTestSample,
    CultivationWasteRecord,
    MetrcTagInventory,
)
from modules.regulatory.metrc_process_readiness import MetrcProcessReadinessService, MetrcTransferReadinessService


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


def test_immature_origin_and_metrc_tag_identity_are_separate_until_vegetative():
    engine = _engine()
    service = MetrcProcessReadinessService(engine)

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

    service.sync_available_tags(
        "org-metrc", "facility-grow",
        jurisdiction_code="MA", license_number="LIC-GROW", environment="sandbox",
        plant_records=[{"label": "1A40-PLANT-001"}, {"label": "1A40-PLANT-002"}, {"label": "1A40-PLANT-003"}],
        package_records=[{"label": "1A40-TEST-001"}],
    )
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


def test_harvest_requires_every_plant_wet_weight_and_structured_process_records():
    engine = _engine()
    readiness = MetrcProcessReadinessService(engine)
    cultivation = CultivationService(engine)
    readiness.sync_available_tags(
        "org-metrc", "facility-grow", jurisdiction_code="MA", license_number="LIC-GROW", environment="sandbox",
        plant_records=[{"label": "P-1"}, {"label": "P-2"}], package_records=[{"label": "TEST-1"}],
    )
    group = readiness.create_immature_group(
        "org-metrc", "facility-grow",
        group_code="SEEDS-1", group_type="seed_batch", strain_name="Blue Dream", quantity=2,
        origin_type="beginning_inventory", origin_reference="BI-2026-001", actor="grower",
    )
    veg = readiness.assign_vegetative_tags(
        "org-metrc", "facility-grow", group["id"], environment="sandbox", actor="grower", provider_confirmed=True,
    )
    for row in veg["plants"]:
        cultivation.transition("org-metrc", "facility-grow", row["id"], phase="flowering", room_code="FLOWER-A", actor="grower")
    harvest = cultivation.create_harvest(
        "org-metrc", "facility-grow", harvest_code="HARV-1",
        plant_ids=[row["id"] for row in veg["plants"]], actor="grower",
    )
    with pytest.raises(ValueError, match="exactly every plant"):
        readiness.record_harvest_wet_weights(
            "org-metrc", "facility-grow", harvest["id"],
            plant_weights=[{"plant_id": veg["plants"][0]["id"], "wet_weight_g": 400}],
            actor="grower", provider_confirmed=True,
        )
    result = readiness.record_harvest_wet_weights(
        "org-metrc", "facility-grow", harvest["id"],
        plant_weights=[
            {"plant_id": veg["plants"][0]["id"], "wet_weight_g": 400},
            {"plant_id": veg["plants"][1]["id"], "wet_weight_g": 350},
        ],
        actor="grower", provider_confirmed=True,
    )
    assert result["wet_weight_g"] == pytest.approx(750)

    waste = readiness.record_waste(
        "org-metrc", "facility-grow", actor="grower", provider_confirmed=True,
        target_type="harvest", target_id=harvest["id"], method="Grind and mix",
        material_mixed="non-cannabis waste", weight=25, unit="g", reason="Stem/leaf waste",
        waste_date=date.today(), location="DRY-A", notes="",
    )
    assert waste["weight"] == 25

    # Use a fresh veg group to exercise manicure separately from harvest/waste.
    second = readiness.create_immature_group(
        "org-metrc", "facility-grow",
        group_code="CLONES-2", group_type="clone_batch", strain_name="GMO", quantity=1,
        origin_type="source_package", origin_reference="1A40-PACKAGE-001",
        source_lot_id="source-package", actor="grower",
    )
    readiness.sync_available_tags(
        "org-metrc", "facility-grow", jurisdiction_code="MA", license_number="LIC-GROW", environment="sandbox",
        plant_records=[{"label": "P-3"}], package_records=[{"label": "TEST-1"}],
    )
    second = readiness.assign_vegetative_tags(
        "org-metrc", "facility-grow", second["id"], environment="sandbox", actor="grower", provider_confirmed=True,
        tag_labels=["P-3"],
    )
    manicure = readiness.create_manicure_batch(
        "org-metrc", "facility-grow", batch_code="MAN-1", source_phase="vegetative", location="VEG-A",
        manicure_date=date.today(), plant_weights=[{"plant_id": second["plants"][0]["id"], "weight_g": 12.5}],
        notes="Usable material removed before harvest", actor="grower", provider_confirmed=True,
    )
    assert manicure["total_weight_g"] == pytest.approx(12.5)

    additive = readiness.record_additive(
        "org-metrc", "facility-grow", actor="grower", target_type="plant",
        target_id=second["plants"][0]["id"], product_name="Nutrient A", epa_number="",
        supplier="Vendor", amount=10, unit="mL", active_ingredients="", application_date=date.today(), notes="",
    )
    assert additive["product_name"] == "Nutrient A"

    sample = readiness.create_test_sample(
        "org-metrc", "facility-grow", environment="sandbox", source_type="harvest", source_id=harvest["id"],
        package_tag="TEST-1", quantity=5, unit="g", actor="qa", provider_confirmed=False,
    )
    assert sample["status"] == "planned"
    confirmed = readiness.confirm_test_sample(
        "org-metrc", "facility-grow", sample["id"], provider_reference="METRC-SAMPLE-1", actor="qa",
    )
    assert confirmed["status"] == "provider_confirmed"

    with Session(engine) as session:
        assert session.scalar(select(func.count(CultivationHarvestPlantWeight.id))) == 2
        assert session.scalar(select(func.count(CultivationWasteRecord.id))) == 1
        assert session.scalar(select(func.count(CultivationManicureBatch.id))) == 1
        assert session.scalar(select(func.count(CultivationAdditiveApplication.id))) == 1
        assert session.scalar(select(func.count(CultivationTestSample.id))) == 1


def test_strict_metrc_transfer_blocks_partial_preserves_package_and_handles_rejected_return():
    engine = _engine()
    service = MetrcTransferReadinessService(engine)

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
    assert transfer["metrc_control"]["provider_status"] == "prepared"
    assert _balance(engine, "source-package") == pytest.approx(0)

    transfer = service.confirm_departure("org-metrc", "facility-grow", transfer["id"], actor="driver")
    assert transfer["metrc_control"]["provider_status"] == "departed"
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
    service = MetrcTransferReadinessService(engine)
    transfer = service.dispatch_whole_packages(
        "org-metrc", "facility-grow", destination_facility_id="facility-retail",
        manifest_reference="MAN-RECEIVE", lines=[{"source_lot_id": "source-package", "quantity": 100}], actor="shipper",
    )
    line = transfer["lines"][0]
    service.confirm_departure("org-metrc", "facility-grow", transfer["id"], actor="driver")
    received = service.receive_whole_package(
        "org-metrc", "facility-retail", transfer["id"], line["id"], operation="retail", actor="receiver",
        location="RECEIVING",
    )
    received_line = received["lines"][0]
    with Session(engine) as session:
        lot = session.get(InventoryLot, received_line["destination_lot_id"])
        assert lot.compliance_package_id == "1A40-PACKAGE-001"
        assert _balance(engine, lot.id) == pytest.approx(100)
