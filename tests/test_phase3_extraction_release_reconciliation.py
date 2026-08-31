from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.extraction.models import ExtractionRun, ExtractionStageEvent
from modules.extraction.repository import ExtractionRepository
from modules.material_lineage.models import MaterialTransformation, MaterialTransformationLoss


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def test_final_qa_release_persists_system_derived_residual_instead_of_losing_mass():
    engine = _engine()
    with Session(engine) as session, session.begin():
        organization = Organization(name="Extraction Release Reconciliation", slug="extraction-release-reconciliation")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Manufacturing",
            code="MFG-REL",
            production_enabled=True,
        )
        source_product = Product(
            organization_id=organization.id,
            sku="REL-BIOMASS",
            name="Release Biomass",
            item_type="cannabis",
            base_unit="g",
            unit_cost=1.0,
        )
        final_product = Product(
            organization_id=organization.id,
            sku="REL-BULK",
            name="Released Bulk Extract",
            item_type="finished_good",
            base_unit="g",
        )
        session.add_all([facility, source_product, final_product])
        session.flush()
        source_lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=source_product.id,
            lot_code="REL-SOURCE-LOT",
            location_code="VAULT",
            status="available",
        )
        session.add(source_lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=source_lot.id,
                transaction_type="receipt",
                quantity_delta=20,
                unit="g",
                actor="seed",
            )
        )
        organization_id = organization.id
        facility_id = facility.id
        source_lot_id = source_lot.id
        final_product_id = final_product.id

    repo = ExtractionRepository(engine)
    run = repo.create_run(
        organization_id=organization_id,
        facility_id=facility_id,
        batch_number="EXT-REL-001",
        method="Ethanol",
        workflow_key="ethanol_crude",
        actor="operator",
    )
    reserved = repo.reserve_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        lot_id=source_lot_id,
        quantity=20,
        unit="g",
        actor="operator",
    )
    repo.consume_input(
        organization_id=organization_id,
        facility_id=facility_id,
        run_input_id=reserved.id,
        quantity=20,
        actor="operator",
    )
    output = repo.create_output(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        product_id=final_product_id,
        lot_code="REL-FINAL-LOT",
        quantity=8,
        unit="g",
        actor="operator",
    )
    repo.record_qa_event(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        output_id=output.id,
        event_type="coa_attached",
        result="passed",
        coa_reference="COA-REL-001",
        actor="qa@example.com",
    )
    repo.record_qa_event(
        organization_id=organization_id,
        facility_id=facility_id,
        run_id=run.id,
        event_type="release",
        result="passed",
        actor="qa@example.com",
    )

    with Session(engine) as session:
        saved_run = session.get(ExtractionRun, run.id)
        reconciliation = session.scalar(
            select(ExtractionStageEvent).where(
                ExtractionStageEvent.run_id == run.id,
                ExtractionStageEvent.loss_reason == "System-derived unclassified extraction closeout residual",
            )
        )
        transformation = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.transformation_type == "extraction_run",
                MaterialTransformation.source_entity_id == run.id,
            )
        )
        loss = session.scalar(
            select(MaterialTransformationLoss).where(
                MaterialTransformationLoss.transformation_id == transformation.id,
                MaterialTransformationLoss.loss_type == "extraction_process_loss",
            )
        )
        assert saved_run.status == "complete"
        assert saved_run.release_status == "approved"
        assert reconciliation is not None
        assert reconciliation.loss_weight_g == 12
        assert "not an external waste/disposal submission" in reconciliation.notes
        assert transformation.status == "committed"
        assert loss.quantity == 12
