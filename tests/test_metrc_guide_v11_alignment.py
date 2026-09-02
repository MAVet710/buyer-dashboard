from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.cultivation.service import CultivationService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.material_lineage.models import MaterialTransformationLoss
from modules.regulatory.metrc_guide_v11 import MetrcGuideV11Service, MetrcGuideV11TransferService
from modules.regulatory.metrc_guide_v11_models import MetrcHarvestWasteProjection
from modules.regulatory.metrc_process_models import MetrcTagInventory


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-guide", name="Guide Alignment", slug="guide-alignment"))
        session.add_all([
            Facility(
                id="grow-guide", organization_id="org-guide", name="Grow", code="GROW-G",
                license_number="LIC-GROW-G", license_type="Cultivator",
                cultivation_enabled=True, production_enabled=True, retail_enabled=False,
            ),
            Facility(
                id="retail-guide", organization_id="org-guide", name="Retail", code="RETAIL-G",
                license_number="LIC-RETAIL-G", license_type="Retailer",
                cultivation_enabled=False, production_enabled=False, retail_enabled=True,
            ),
        ])
        product = Product(
            id="flower-guide", organization_id="org-guide", sku="FLOWER-G", name="Flower",
            item_type="cannabis", base_unit="g", unit_cost=2.0,
        )
        session.add(product)
        session.flush()
        lot = InventoryLot(
            id="source-guide", organization_id="org-guide", facility_id="grow-guide",
            product_id=product.id, lot_code="SOURCE-G", compliance_package_id="METRC-SOURCE-G",
            external_inventory_id="METRC-SOURCE-G", barcode_value="METRC-SOURCE-G",
            location_code="VAULT", status="released",
        )
        session.add(lot)
        session.flush()
        session.add(InventoryTransaction(
            organization_id="org-guide", facility_id="grow-guide", lot_id=lot.id,
            transaction_type="receipt", quantity_delta=453.6, unit="g", actor="seed",
        ))
    return engine


def _sync(service: MetrcGuideV11Service, tags: list[str]) -> None:
    service.sync_available_tags(
        "org-guide", "grow-guide", jurisdiction_code="MA", license_number="LIC-GROW-G",
        environment="sandbox", plant_records=[{"label": tag} for tag in tags], package_records=[],
    )


def _harvest(engine, service: MetrcGuideV11Service, *, tags: list[str], code: str):
    _sync(service, tags)
    group = service.create_immature_group(
        "org-guide", "grow-guide", group_code=f"G-{code}", group_type="clone_batch",
        strain_name="GMO", quantity=len(tags), origin_type="source_package",
        origin_reference="METRC-SOURCE-G", source_lot_id="source-guide", actor="grower",
    )
    group = service.assign_vegetative_tags(
        "org-guide", "grow-guide", group["id"], environment="sandbox", actor="grower",
        provider_confirmed=True, tag_labels=tags,
    )
    cultivation = CultivationService(engine)
    for plant in group["plants"]:
        cultivation.transition(
            "org-guide", "grow-guide", plant["id"], phase="flowering", room_code="FLOWER-A", actor="grower"
        )
    harvest = cultivation.create_harvest(
        "org-guide", "grow-guide", harvest_code=code,
        plant_ids=[row["id"] for row in group["plants"]], actor="grower",
    )
    service.record_harvest_wet_weights(
        "org-guide", "grow-guide", harvest["id"],
        plant_weights=[{"plant_id": row["id"], "wet_weight_g": 100.0} for row in group["plants"]],
        actor="grower", provider_confirmed=True,
    )
    return group, harvest


def _package_harvest(engine, harvest_id: str, quantity: float) -> None:
    allocation = GuardedHarvestAllocationService(engine)
    preview = allocation.preview_harvest_allocation(
        organization_id="org-guide", facility_id="grow-guide", harvest_id=harvest_id,
        outputs=[{
            "product_id": "flower-guide", "lot_code": f"OUT-{harvest_id[:8]}", "quantity": quantity,
            "unit": "g", "purpose": "finished_flower", "measurement_basis": "wet",
            "status": "quarantine", "location_code": "DRY", "compliance_package_id": f"PKG-{harvest_id[:8]}",
        }], losses=[],
    )
    allocation.commit_harvest_allocation(
        organization_id="org-guide", facility_id="grow-guide", harvest_id=harvest_id,
        outputs=preview["outputs"], losses=[], preview_key=preview["preview_key"], actor="grower",
    )


def test_finish_flushes_moisture_before_closeout_guard_and_unfinish_restores_active_balance():
    engine = _engine()
    service = MetrcGuideV11Service(engine)
    _, harvest = _harvest(engine, service, tags=["P1", "P2"], code="HARV-FINISH")
    _package_harvest(engine, harvest["id"], 150.0)

    closed = service.finish_harvest(
        "org-guide", "grow-guide", harvest["id"], actor="grower",
        provider_confirmed=True, all_waste_reported=True,
    )
    assert closed["status"] == "completed"
    assert closed["existing_moisture_loss_g"] == pytest.approx(50.0)

    reopened = service.unfinish_harvest(
        "org-guide", "grow-guide", harvest["id"], actor="grower",
        provider_confirmed=True, provider_reference="METRC-UNFINISH-1",
    )
    assert reopened["status"] == "active"
    assert reopened["restored_moisture_loss_g"] == pytest.approx(50.0)
    preview = service.harvest_closeout_preview("org-guide", "grow-guide", harvest["id"])
    assert preview["remaining_for_moisture_loss_g"] == pytest.approx(50.0)


def test_discontinue_harvest_waste_restores_weight_without_erasing_audit_record():
    engine = _engine()
    service = MetrcGuideV11Service(engine)
    _, harvest = _harvest(engine, service, tags=["W1"], code="HARV-WASTE")
    waste = service.record_waste(
        "org-guide", "grow-guide", actor="grower", provider_confirmed=True,
        target_type="harvest", target_id=harvest["id"], method="Grind", material_mixed="waste",
        weight=20.0, unit="g", reason="Stem", waste_date=date.today(), location="DRY",
        measurement_basis="wet", notes="",
    )
    before = service.harvest_closeout_preview("org-guide", "grow-guide", harvest["id"])
    assert before["reported_loss_or_waste_g"] == pytest.approx(20.0)
    assert before["structured_waste_record_count"] == 1

    result = service.discontinue_harvest_waste(
        "org-guide", "grow-guide", harvest["id"], waste["id"], actor="grower",
        provider_confirmed=True, provider_reference="METRC-WASTE-X",
    )
    assert result["restored_weight_g"] == pytest.approx(20.0)
    after = service.harvest_closeout_preview("org-guide", "grow-guide", harvest["id"])
    assert after["reported_loss_or_waste_g"] == pytest.approx(0.0)
    assert after["structured_waste_record_count"] == 0
    with Session(engine) as session:
        projection = session.scalar(select(MetrcHarvestWasteProjection))
        assert projection.discontinued_at is not None
        assert session.get(MaterialTransformationLoss, projection.material_loss_id).quantity == pytest.approx(0.0)


def test_receiving_variance_requires_documented_guide_exception_and_preserves_manifested_tag():
    engine = _engine()
    service = MetrcGuideV11TransferService(engine)
    transfer = service.dispatch_whole_packages(
        "org-guide", "grow-guide", destination_facility_id="retail-guide", manifest_reference="MAN-GUIDE",
        provider_transfer_id="METRC-XFER", lines=[{"source_lot_id": "source-guide", "quantity": 453.6}], actor="shipper",
    )
    line_id = transfer["lines"][0]["id"]
    with pytest.raises(ValueError, match="only for documented scale variance"):
        service.receive_manifested_package(
            "org-guide", "retail-guide", transfer["id"], line_id,
            operation="retail", actor="receiver", received_quantity=450.0, received_unit="g",
        )

    received = service.receive_manifested_package(
        "org-guide", "retail-guide", transfer["id"], line_id,
        operation="retail", actor="receiver", received_quantity=1.0, received_unit="lb",
        variance_reason="uom_conversion",
    )
    line = received["lines"][0]
    assert line["destination_package_id"] == "METRC-SOURCE-G"
    assert line["received_quantity"] == pytest.approx(453.6)
    with Session(engine) as session:
        destination = session.get(InventoryLot, line["destination_lot_id"])
        assert destination.compliance_package_id == "METRC-SOURCE-G"


def test_tag_sync_model_is_loaded_with_guide_tables():
    engine = _engine()
    service = MetrcGuideV11Service(engine)
    _sync(service, ["TAG-GUIDE"])
    with Session(engine) as session:
        assert session.scalar(select(func.count(MetrcTagInventory.id))) == 1
        assert MetrcHarvestWasteProjection.__table__.name in Base.metadata.tables
