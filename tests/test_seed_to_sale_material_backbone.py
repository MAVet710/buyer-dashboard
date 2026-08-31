from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import Base, InventoryLot, MaterialReservation, Product
from modules.cultivation.service import CultivationService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService
from modules.material_lineage.models import MaterialTransformation, MaterialTransformationInput, MaterialTransformationOutput
from modules.material_lineage.service import MaterialLineageService
from modules.production_erp.run360_mutations import ProductionRun360MutationService
from modules.production_erp.service import ProductionERPService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _vertical_scope(engine):
    repo = ComanRepository(engine)
    organization = repo.create_organization("Seed to Sale QA")
    facility = repo.create_facility(organization.id, "Vertical Facility", "VERTICAL")
    with Session(engine) as session, session.begin():
        row = session.get(type(facility), facility.id)
        row.cultivation_enabled = True
        row.production_enabled = True
        row.retail_enabled = True
        row.commercial_enabled = True
    return repo, organization, facility


def test_allocated_harvest_can_complete_and_traces_inventory_to_source_plants():
    engine = _engine()
    repo, organization, facility = _vertical_scope(engine)
    bulk = repo.create_product(
        organization.id,
        sku="BULK-GP",
        name="Gastro Pop Bulk Flower",
        item_type="cannabis",
        base_unit="g",
        unit_cost=0,
        actor="qa",
    )
    cultivation = CultivationService(engine)
    first = cultivation.create_plant(
        organization.id,
        facility.id,
        plant_tag="GP-001",
        strain_name="Gastro Pop",
        phase="flowering",
        room_code="FLOWER-A",
        actor="qa",
    )
    second = cultivation.create_plant(
        organization.id,
        facility.id,
        plant_tag="GP-002",
        strain_name="Gastro Pop",
        phase="flowering",
        room_code="FLOWER-A",
        actor="qa",
    )
    harvest = cultivation.create_harvest(
        organization.id,
        facility.id,
        harvest_code="GP-0830",
        plant_ids=[first.id, second.id],
        actor="qa",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="active",
        actor="qa",
        wet_weight=1000,
        unit="g",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="drying",
        actor="qa",
        dry_weight=250,
        unit="g",
    )

    lineage = GuardedHarvestAllocationService(engine)
    outputs = [{
        "product_id": bulk.id,
        "lot_code": "GP-0830-FLOWER",
        "quantity": 200,
        "unit": "g",
        "purpose": "finished_flower",
        "measurement_basis": "dry",
        "status": "quarantine",
        "location_code": "DRY-ROOM-1",
    }]
    losses = [{
        "quantity": 50,
        "unit": "g",
        "loss_type": "drying_loss",
        "measurement_basis": "dry",
        "reason": "Measured closeout loss",
    }]
    preview = lineage.preview_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=losses,
    )
    assert preview["reconciliation"]["dry"]["remaining"] == 0
    assert preview["preview_key"]

    committed = lineage.commit_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=losses,
        preview_key=preview["preview_key"],
        actor="qa",
    )
    completed = cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="completed",
        actor="qa",
    )
    assert completed["status"] == "completed"

    lot_id = committed["output_lot_ids"][0]
    assert repo.inventory_balance(organization.id, lot_id) == 200

    graph = MaterialLineageService(engine).lot_graph(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=lot_id,
    )
    assert any(node["type"] == "harvest" and node["harvest_code"] == "GP-0830" for node in graph["nodes"])
    assert {node.get("plant_tag") for node in graph["nodes"] if node["type"] == "plant"} == {"GP-001", "GP-002"}
    assert any(edge["relationship"] == "produced" for edge in graph["edges"])

    with Session(engine) as session:
        transformation = session.scalar(
            select(MaterialTransformation).where(MaterialTransformation.source_entity_id == harvest["id"])
        )
        assert transformation is not None
        assert len(list(session.scalars(select(MaterialTransformationInput).where(MaterialTransformationInput.transformation_id == transformation.id)))) == 2
        assert len(list(session.scalars(select(MaterialTransformationOutput).where(MaterialTransformationOutput.transformation_id == transformation.id)))) == 1

    with pytest.raises(ValueError, match="exceed measured dry weight"):
        lineage.preview_harvest_allocation(
            organization_id=organization.id,
            facility_id=facility.id,
            harvest_id=harvest["id"],
            outputs=[{
                "product_id": bulk.id,
                "lot_code": "GP-0830-OVER",
                "quantity": 1,
                "unit": "g",
                "purpose": "smalls",
                "measurement_basis": "dry",
            }],
            losses=[],
        )


def test_production_actual_consumption_decrements_source_and_finished_output_keeps_genealogy():
    engine = _engine()
    repo, organization, facility = _vertical_scope(engine)
    material = repo.create_product(
        organization.id,
        sku="MAT-GP",
        name="Gastro Pop Bulk Flower",
        item_type="cannabis",
        base_unit="g",
        unit_cost=1,
        actor="qa",
    )
    finished = repo.create_product(
        organization.id,
        sku="PR-GP",
        name="Gastro Pop Pre-Roll",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=0,
        actor="qa",
    )
    source = repo.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=material.id,
        lot_code="GP-SOURCE",
        opening_quantity=100,
        unit="g",
        actor="qa",
    )
    repo.create_bom(
        organization.id,
        output_product_id=finished.id,
        output_quantity=10,
        expected_loss_pct=0,
        components=[{"input_product_id": material.id, "quantity": 10, "unit": "g"}],
        actor="qa",
    )
    order = repo.create_production_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number="RUN-GP-001",
        work_type="internal",
        product_name=finished.name,
        product_format="Pre-Roll",
        requested_units=10,
        sku=finished.sku,
        actor="qa",
    )
    erp = ProductionERPService(engine)
    assert erp.reserve_bom_materials(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        actor="qa",
    )["shortages"] == []

    mutations = ProductionRun360MutationService(engine)
    completion_before = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="run_event",
        payload={"event_type": "completed"},
    )
    assert completion_before["blocker_count"] >= 1
    assert any("Record actual consumption" in row["message"] for row in completion_before["warnings"])

    consume_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="consume_materials",
        payload={"materials": [{"lot_id": source.id, "quantity": 10, "unit": "g"}]},
    )
    assert consume_preview["blocker_count"] == 0
    consume = mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="consume_materials",
        payload={"materials": [{"lot_id": source.id, "quantity": 10, "unit": "g"}]},
        preview_key=consume_preview["preview_key"],
        actor="qa",
    )
    assert consume["result"]["consumed"][0]["quantity"] == 10
    assert repo.inventory_balance(organization.id, source.id) == 90
    with Session(engine) as session:
        reservation = session.scalar(
            select(MaterialReservation).where(MaterialReservation.production_order_id == order.id)
        )
        assert reservation is not None
        assert reservation.quantity == 0
        assert reservation.status == "consumed"

    output = erp.add_output(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        product_id=finished.id,
        planned_quantity=10,
        actor="qa",
        unit="unit",
    )
    output_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="record_output_actual",
        payload={"output_id": output.id, "actual_quantity": 9, "lot_code": "PR-GP-OUT"},
    )
    output_commit = mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="record_output_actual",
        payload={"output_id": output.id, "actual_quantity": 9, "lot_code": "PR-GP-OUT"},
        preview_key=output_preview["preview_key"],
        actor="qa",
    )
    output_lot_id = output_commit["result"]["lot_id"]
    assert repo.inventory_balance(organization.id, output_lot_id) == 9

    release_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="qa_decision",
        payload={"event_type": "release", "result": "passed", "output_id": output.id},
    )
    assert release_preview["blocker_count"] == 0
    mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="qa_decision",
        payload={"event_type": "release", "result": "passed", "output_id": output.id},
        preview_key=release_preview["preview_key"],
        actor="qa",
    )

    graph = MaterialLineageService(engine).lot_graph(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=output_lot_id,
    )
    assert any(node["type"] == "lot" and node["id"] == source.id for node in graph["nodes"])
    assert any(node["type"] == "production_order" and node["order_number"] == "RUN-GP-001" for node in graph["nodes"])
    assert any(edge["from"] == f"lot:{source.id}" and edge["relationship"] == "consumed" for edge in graph["edges"])

    completion_after = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="run_event",
        payload={"event_type": "completed"},
    )
    assert completion_after["blocker_count"] == 0


def test_vertical_journey_traces_finished_good_back_through_production_harvest_and_plants():
    engine = _engine()
    repo, organization, facility = _vertical_scope(engine)
    bulk = repo.create_product(
        organization.id,
        sku="VERT-BULK",
        name="Vertical Kush Bulk Flower",
        item_type="cannabis",
        base_unit="g",
        unit_cost=1,
        actor="qa",
    )
    finished = repo.create_product(
        organization.id,
        sku="VERT-PR",
        name="Vertical Kush Pre-Roll",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=0,
        actor="qa",
    )
    cultivation = CultivationService(engine)
    plants = [
        cultivation.create_plant(
            organization.id,
            facility.id,
            plant_tag=f"VERT-{index}",
            strain_name="Vertical Kush",
            phase="flowering",
            room_code="FLOWER-V",
            actor="qa",
        )
        for index in range(1, 3)
    ]
    harvest = cultivation.create_harvest(
        organization.id,
        facility.id,
        harvest_code="VERT-H-001",
        plant_ids=[plant.id for plant in plants],
        actor="qa",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="active",
        actor="qa",
        wet_weight=500,
        unit="g",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="drying",
        actor="qa",
        dry_weight=100,
        unit="g",
    )

    harvest_lineage = GuardedHarvestAllocationService(engine)
    harvest_outputs = [{
        "product_id": bulk.id,
        "lot_code": "VERT-H-001-BULK",
        "quantity": 100,
        "unit": "g",
        "purpose": "finished_flower",
        "measurement_basis": "dry",
        "status": "available",
        "location_code": "BULK-VAULT",
    }]
    harvest_preview = harvest_lineage.preview_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=harvest_outputs,
        losses=[],
    )
    harvest_commit = harvest_lineage.commit_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=harvest_outputs,
        losses=[],
        preview_key=harvest_preview["preview_key"],
        actor="qa",
    )
    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="completed",
        actor="qa",
    )
    bulk_lot_id = harvest_commit["output_lot_ids"][0]
    assert repo.inventory_balance(organization.id, bulk_lot_id) == 100

    repo.create_bom(
        organization.id,
        output_product_id=finished.id,
        output_quantity=10,
        expected_loss_pct=0,
        components=[{"input_product_id": bulk.id, "quantity": 10, "unit": "g"}],
        actor="qa",
    )
    order = repo.create_production_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number="VERT-RUN-001",
        work_type="internal",
        product_name=finished.name,
        product_format="Pre-Roll",
        requested_units=10,
        sku=finished.sku,
        actor="qa",
    )
    mutations = ProductionRun360MutationService(engine)
    reserve_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="reserve_materials",
        payload={},
    )
    assert reserve_preview["blocker_count"] == 0
    mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="reserve_materials",
        payload={},
        preview_key=reserve_preview["preview_key"],
        actor="qa",
    )
    consume_payload = {"materials": [{"lot_id": bulk_lot_id, "quantity": 10, "unit": "g"}]}
    consume_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="consume_materials",
        payload=consume_payload,
    )
    assert consume_preview["blocker_count"] == 0
    mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="consume_materials",
        payload=consume_payload,
        preview_key=consume_preview["preview_key"],
        actor="qa",
    )
    assert repo.inventory_balance(organization.id, bulk_lot_id) == 90

    erp = ProductionERPService(engine)
    output = erp.add_output(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        product_id=finished.id,
        planned_quantity=10,
        actor="qa",
        unit="unit",
    )
    output_payload = {"output_id": output.id, "actual_quantity": 10, "lot_code": "VERT-FINISHED-001"}
    output_preview = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="record_output_actual",
        payload=output_payload,
    )
    output_commit = mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="record_output_actual",
        payload=output_payload,
        preview_key=output_preview["preview_key"],
        actor="qa",
    )
    finished_lot_id = output_commit["result"]["lot_id"]
    assert repo.inventory_balance(organization.id, finished_lot_id) == 10

    completion = mutations.preview(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="run_event",
        payload={"event_type": "completed"},
    )
    assert completion["blocker_count"] == 0
    mutations.commit(
        organization_id=organization.id,
        facility_id=facility.id,
        order_id=order.id,
        action_type="run_event",
        payload={"event_type": "completed"},
        preview_key=completion["preview_key"],
        actor="qa",
    )

    graph = MaterialLineageService(engine).lot_graph(
        organization_id=organization.id,
        facility_id=facility.id,
        lot_id=finished_lot_id,
    )
    assert any(node["type"] == "production_order" and node["order_number"] == "VERT-RUN-001" for node in graph["nodes"])
    assert any(node["type"] == "harvest" and node["harvest_code"] == "VERT-H-001" for node in graph["nodes"])
    assert any(node["type"] == "lot" and node["id"] == bulk_lot_id for node in graph["nodes"])
    assert {node.get("plant_tag") for node in graph["nodes"] if node["type"] == "plant"} == {"VERT-1", "VERT-2"}
    assert any(edge["from"] == f"lot:{bulk_lot_id}" and edge["relationship"] == "consumed" for edge in graph["edges"])


def test_lineage_and_consumption_are_facility_scoped():
    engine = _engine()
    repo, organization, facility = _vertical_scope(engine)
    material = repo.create_product(
        organization.id,
        sku="SCOPE-MAT",
        name="Scoped Material",
        item_type="cannabis",
        base_unit="g",
        unit_cost=1,
        actor="qa",
    )
    lot = repo.create_inventory_lot(
        organization.id,
        facility.id,
        product_id=material.id,
        lot_code="SCOPE-LOT",
        opening_quantity=25,
        unit="g",
        actor="qa",
    )
    other = repo.create_organization("Other Tenant")
    other_facility = repo.create_facility(other.id, "Other", "OTHER")
    with pytest.raises(ValueError, match="active facility"):
        MaterialLineageService(engine).lot_graph(
            organization_id=other.id,
            facility_id=other_facility.id,
            lot_id=lot.id,
        )
