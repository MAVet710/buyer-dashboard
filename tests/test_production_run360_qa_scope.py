from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization, Product, ProductionOrder
from modules.production_erp.models import ProductionRunOutput
from modules.production_erp.run360_mutations import ProductionRun360MutationService


def test_whole_run_qa_hold_does_not_quarantine_unrealized_planned_output():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="QA Scope", slug="qa-scope")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Production",
            code="PROD",
            production_enabled=True,
            retail_enabled=False,
        )
        product = Product(
            organization_id=organization.id,
            sku="FG-QA",
            name="QA Finished Good",
            item_type="finished_good",
            base_unit="each",
        )
        session.add_all([facility, product])
        session.flush()
        order = ProductionOrder(
            organization_id=organization.id,
            facility_id=facility.id,
            order_number="QA-RUN-1",
            work_type="internal",
            product_name=product.name,
            sku=product.sku,
            product_format="finished good",
            requested_units=100,
            priority="normal",
            status="in_progress",
            created_by="seed",
            updated_by="seed",
        )
        session.add(order)
        session.flush()
        output = ProductionRunOutput(
            organization_id=organization.id,
            facility_id=facility.id,
            production_order_id=order.id,
            product_id=product.id,
            position=1,
            label="Planned Only",
            planned_quantity=100,
            actual_quantity=0,
            unit="each",
            status="planned",
            created_by="seed",
        )
        session.add(output)
        session.commit()
        org_id, facility_id, order_id, output_id = organization.id, facility.id, order.id, output.id

    service = ProductionRun360MutationService(engine)
    payload = {
        "event_type": "hold",
        "result": "pending",
        "output_id": None,
        "document_reference": "",
        "notes": "Whole-run QA hold",
    }
    preview = service.preview(
        organization_id=org_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="qa_decision",
        payload=payload,
    )
    assert preview["details"]["target_output_ids"] == []
    assert not any(row["after"] == "Quarantine / unavailable" for row in preview["consequences"])

    service.commit(
        organization_id=org_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="qa_decision",
        payload=payload,
        preview_key=preview["preview_key"],
        actor="qa-user",
    )
    with Session(engine) as session:
        saved_order = session.get(ProductionOrder, order_id)
        saved_output = session.get(ProductionRunOutput, output_id)
        assert saved_order.status == "on_hold"
        assert saved_output.status == "planned"
        assert saved_output.actual_quantity == 0
        assert saved_output.lot_id is None
