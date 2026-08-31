from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.production_mutations import _guard_mutation
from modules.coman import ComanRepository
from modules.coman.models import Base
from modules.cultivation.service import CultivationService
from modules.material_lineage.harvest_guard import GuardedHarvestAllocationService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    repo = ComanRepository(engine)
    organization = repo.create_organization("Preview Guard QA")
    facility = repo.create_facility(organization.id, "Vertical", "VERT")
    with Session(engine) as session, session.begin():
        row = session.get(type(facility), facility.id)
        row.cultivation_enabled = True
        row.production_enabled = True
    product = repo.create_product(
        organization.id,
        sku="HARV-OUT",
        name="Harvest Output",
        item_type="cannabis",
        base_unit="g",
        unit_cost=0,
        actor="qa",
    )
    cultivation = CultivationService(engine)
    plant = cultivation.create_plant(
        organization.id,
        facility.id,
        plant_tag="GUARD-001",
        strain_name="Gastro Pop",
        phase="flowering",
        room_code="FLOWER-A",
        actor="qa",
    )
    harvest = cultivation.create_harvest(
        organization.id,
        facility.id,
        harvest_code="GUARD-HARVEST",
        plant_ids=[plant.id],
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
    return repo, organization, facility, product, harvest, cultivation


def test_harvest_commit_rejects_preview_after_measured_weight_changes():
    engine = _engine()
    _repo, organization, facility, product, harvest, cultivation = _scope(engine)
    service = GuardedHarvestAllocationService(engine)
    outputs = [{
        "product_id": product.id,
        "lot_code": "GUARD-LOT",
        "quantity": 80,
        "unit": "g",
        "purpose": "finished_flower",
        "measurement_basis": "dry",
        "status": "quarantine",
        "location_code": "DRY-ROOM",
    }]
    preview = service.preview_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=[],
    )
    assert preview["preview_key"]

    cultivation.transition_harvest(
        organization.id,
        facility.id,
        harvest["id"],
        status="drying",
        actor="qa",
        dry_weight=90,
        unit="g",
    )

    with pytest.raises(ValueError, match="preview is stale"):
        service.commit_harvest_allocation(
            organization_id=organization.id,
            facility_id=facility.id,
            harvest_id=harvest["id"],
            outputs=outputs,
            losses=[],
            preview_key=preview["preview_key"],
            actor="qa",
        )


def test_current_harvest_preview_can_commit_exact_allocation():
    engine = _engine()
    repo, organization, facility, product, harvest, _cultivation = _scope(engine)
    service = GuardedHarvestAllocationService(engine)
    outputs = [{
        "product_id": product.id,
        "lot_code": "GUARD-CURRENT",
        "quantity": 80,
        "unit": "g",
        "purpose": "finished_flower",
        "measurement_basis": "dry",
        "status": "quarantine",
        "location_code": "DRY-ROOM",
    }]
    losses = [{
        "quantity": 20,
        "unit": "g",
        "loss_type": "drying_loss",
        "measurement_basis": "dry",
        "reason": "Measured closeout",
    }]
    preview = service.preview_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=losses,
    )
    result = service.commit_harvest_allocation(
        organization_id=organization.id,
        facility_id=facility.id,
        harvest_id=harvest["id"],
        outputs=outputs,
        losses=losses,
        preview_key=preview["preview_key"],
        actor="qa",
    )
    assert len(result["output_lot_ids"]) == 1
    assert repo.inventory_balance(organization.id, result["output_lot_ids"][0]) == 80


def test_planner_cannot_post_physical_consumption_but_operator_can():
    planner = RequestContext("planner", "org", "facility", "planner")
    with pytest.raises(HTTPException) as exc:
        _guard_mutation("consume_materials", planner)
    assert exc.value.status_code == 403

    operator = RequestContext("operator", "org", "facility", "operator")
    _guard_mutation("consume_materials", operator)
