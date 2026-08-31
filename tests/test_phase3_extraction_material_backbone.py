import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.extraction.models import ExtractionRun, ExtractionRunInput, ExtractionRunOutput
from modules.extraction.repository import ExtractionRepository
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.material_lineage.models import (
    MaterialTransformation,
    MaterialTransformationInput,
    MaterialTransformationLoss,
    MaterialTransformationOutput,
)


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _fixture():
    engine = _engine()
    with Session(engine) as session:
        organization = Organization(name="Extraction Backbone QA", slug="extraction-backbone-qa")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Manufacturing",
            code="MFG-1",
            retail_enabled=False,
            production_enabled=True,
        )
        biomass = Product(
            organization_id=organization.id,
            sku="BIO-1",
            name="Biomass",
            item_type="cannabis",
            base_unit="g",
            unit_cost=1.0,
        )
        crude = Product(
            organization_id=organization.id,
            sku="CRUDE-1",
            name="Crude Oil",
            item_type="wip",
            base_unit="g",
        )
        final = Product(
            organization_id=organization.id,
            sku="FINAL-1",
            name="Finished Bulk Oil",
            item_type="finished_good",
            base_unit="g",
        )
        session.add_all([facility, biomass, crude, final])
        session.flush()
        source = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=biomass.id,
            lot_code="BIO-LOT-1",
            compliance_package_id="PKG-BIO-1",
            location_code="VAULT",
            status="available",
        )
        session.add(source)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=source.id,
                transaction_type="receipt",
                quantity_delta=100,
                unit="g",
                actor="seed",
            )
        )
        session.commit()
        return engine, organization.id, facility.id, biomass.id, crude.id, final.id, source.id


def _run(repo: ExtractionRepository, organization_id: str, facility_id: str, *, batch: str, workflow: str, method: str):
    return repo.create_run(
        organization_id=organization_id,
        facility_id=facility_id,
        batch_number=batch,
        workflow_key=workflow,
        method=method,
        actor="operator",
    )


def test_partial_extraction_reservation_is_shared_claim_not_whole_lot_status():
    engine, organization_id, facility_id, _, _, _, source_id = _fixture()
    repo = ExtractionRepository(engine)
    run = _run(repo, organization_id, facility_id, batch="EXT-CLAIM-1", workflow="ethanol_crude", method="Ethanol")
    repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        lot_id=source_id,
        quantity=40,
        unit="g",
        actor="planner",
    )

    with Session(engine) as session:
        lot = session.get(InventoryLot, source_id)
        snapshot = InventoryAvailabilityService.build(session, organization_id, facility_id)
        row = snapshot["by_lot"][source_id]
        assert lot.status == "available"
        assert row["on_hand"] == 100.0
        assert row["extraction_reserved"] == 40.0
        assert row["available"] == 60.0
        assert any(claim["source"] == "extraction" and claim["quantity"] == 40.0 for claim in row["claims"])


def test_actual_extraction_consumption_creates_canonical_input_genealogy():
    engine, organization_id, facility_id, _, _, _, source_id = _fixture()
    repo = ExtractionRepository(engine)
    run = _run(repo, organization_id, facility_id, batch="EXT-CONSUME-1", workflow="ethanol_crude", method="Ethanol")
    reserved = repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        lot_id=source_id,
        quantity=40,
        unit="g",
        actor="planner",
    )
    repo.consume_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_input_id=reserved.id,
        quantity=40,
        actor="operator",
    )

    with Session(engine) as session:
        saved_run = session.get(ExtractionRun, run.id)
        balance = session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == source_id
            )
        )
        transform = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.transformation_type == "extraction_run",
                MaterialTransformation.source_entity_id == run.id,
            )
        )
        lineage_input = session.scalar(
            select(MaterialTransformationInput).where(
                MaterialTransformationInput.transformation_id == transform.id,
                MaterialTransformationInput.lot_id == source_id,
            )
        )
        assert saved_run.status == "active"
        assert float(balance or 0) == 60.0
        assert lineage_input.quantity == 40.0
        assert lineage_input.measurement_basis == "actual"


def test_reconciled_wip_output_closes_upstream_run_and_can_feed_downstream_run():
    engine, organization_id, facility_id, _, crude_id, _, source_id = _fixture()
    repo = ExtractionRepository(engine)
    run = _run(repo, organization_id, facility_id, batch="EXT-WIP-1", workflow="ethanol_crude", method="Ethanol")
    reserved = repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        lot_id=source_id,
        quantity=40,
        unit="g",
        actor="planner",
    )
    repo.consume_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_input_id=reserved.id,
        quantity=40,
        actor="operator",
    )
    repo.record_stage_event(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        stage_key="extraction",
        event_type="completed",
        actor="operator",
        input_weight_g=40,
        output_weight_g=36,
        loss_weight_g=4,
        loss_reason="Measured process loss",
    )
    output = repo.create_output(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        product_id=crude_id,
        lot_code="CRUDE-WIP-1",
        quantity=36,
        unit="g",
        actor="operator",
        output_label="Crude handoff",
    )

    with Session(engine) as session:
        saved_run = session.get(ExtractionRun, run.id)
        saved_output = session.get(ExtractionRunOutput, output.id)
        wip_lot = session.get(InventoryLot, saved_output.lot_id)
        transform = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.transformation_type == "extraction_run",
                MaterialTransformation.source_entity_id == run.id,
            )
        )
        transform_output = session.scalar(
            select(MaterialTransformationOutput).where(
                MaterialTransformationOutput.transformation_id == transform.id,
                MaterialTransformationOutput.lot_id == wip_lot.id,
            )
        )
        loss = session.scalar(
            select(MaterialTransformationLoss).where(
                MaterialTransformationLoss.transformation_id == transform.id,
                MaterialTransformationLoss.loss_type == "extraction_process_loss",
            )
        )
        assert saved_run.status == "complete"
        assert saved_run.current_stage_key == "handoff"
        assert saved_output.status == "released"
        assert wip_lot.status == "available"
        assert transform.status == "committed"
        assert transform_output.purpose == "extraction_intermediate"
        assert loss.quantity == 4.0
        wip_lot_id = wip_lot.id

    downstream = _run(
        repo,
        organization_id,
        facility_id,
        batch="EXT-DOWNSTREAM-1",
        workflow="crude_distillate",
        method="Distillation",
    )
    downstream_input = repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=downstream.id,
        lot_id=wip_lot_id,
        quantity=36,
        unit="g",
        actor="planner",
    )
    with Session(engine) as session:
        row = InventoryAvailabilityService.build(session, organization_id, facility_id)["by_lot"][wip_lot_id]
        assert downstream_input.reserved_quantity == 36
        assert row["extraction_reserved"] == 36
        assert row["available"] == 0


def test_wip_handoff_fails_closed_when_mass_is_not_reconciled():
    engine, organization_id, facility_id, _, crude_id, _, source_id = _fixture()
    repo = ExtractionRepository(engine)
    run = _run(repo, organization_id, facility_id, batch="EXT-WIP-BLOCK", workflow="ethanol_crude", method="Ethanol")
    reserved = repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        lot_id=source_id,
        quantity=40,
        unit="g",
        actor="planner",
    )
    repo.consume_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_input_id=reserved.id,
        quantity=40,
        actor="operator",
    )
    with pytest.raises(ValueError, match="Mass balance"):
        repo.create_output(
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run.id,
            product_id=crude_id,
            lot_code="CRUDE-BAD-1",
            quantity=36,
            unit="g",
            actor="operator",
        )
    with Session(engine) as session:
        assert session.scalar(select(InventoryLot.id).where(InventoryLot.lot_code == "CRUDE-BAD-1")) is None
        assert session.get(ExtractionRun, run.id).status == "active"


def test_direct_complete_cannot_bypass_open_reservation_or_mass_closeout():
    engine, organization_id, facility_id, _, _, final_id, source_id = _fixture()
    repo = ExtractionRepository(engine)
    run = _run(repo, organization_id, facility_id, batch="EXT-CLOSEOUT-GUARD", workflow="ethanol_crude", method="Ethanol")
    repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        lot_id=source_id,
        quantity=20,
        unit="g",
        actor="planner",
    )
    with Session(engine) as session:
        saved = session.get(ExtractionRun, run.id)
        saved.status = "complete"
        with pytest.raises(ValueError, match="closeout is incomplete"):
            session.commit()
        session.rollback()

    # A finished output still follows QA rather than auto-closing like WIP.
    with Session(engine) as session:
        input_row = session.scalar(select(ExtractionRunInput).where(ExtractionRunInput.run_id == run.id))
        input_id = input_row.id
    repo.consume_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_input_id=input_id,
        quantity=20,
        actor="operator",
    )
    repo.record_stage_event(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        stage_key="extraction",
        event_type="completed",
        actor="operator",
        input_weight_g=20,
        output_weight_g=18,
        loss_weight_g=2,
        loss_reason="Measured process loss",
    )
    output = repo.create_output(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        product_id=final_id,
        lot_code="FINAL-QA-1",
        quantity=18,
        unit="g",
        actor="operator",
    )
    with Session(engine) as session:
        saved_run = session.get(ExtractionRun, run.id)
        saved_output = session.get(ExtractionRunOutput, output.id)
        lot = session.get(InventoryLot, saved_output.lot_id)
        assert saved_run.status == "qa"
        assert saved_run.release_status == "pending"
        assert saved_output.status == "quarantine"
        assert lot.status == "quarantine"
