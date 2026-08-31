import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import (
    Base,
    BomComponent,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    ProductBom,
    ProductionOrder,
)
from modules.production_erp.integrity_mutations import ProductionIntegrityMutationService
from modules.production_erp.models import ProductionRunEvent
from modules.production_erp.run360_mutations import ProductionRun360MutationService


def _fixture(*, status: str = "draft"):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="Physical Start QA", slug=f"physical-start-{status}")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Production",
            code="PROD",
            retail_enabled=False,
            production_enabled=True,
        )
        material = Product(
            organization_id=organization.id,
            sku="MAT-START",
            name="Source Material",
            item_type="cannabis",
            base_unit="g",
        )
        finished = Product(
            organization_id=organization.id,
            sku="FG-START",
            name="Finished Good",
            item_type="finished_good",
            base_unit="unit",
        )
        session.add_all([facility, material, finished])
        session.flush()
        bom = ProductBom(
            organization_id=organization.id,
            output_product_id=finished.id,
            version=1,
            output_quantity=10,
            expected_loss_pct=0,
            active=True,
        )
        session.add(bom)
        session.flush()
        session.add(
            BomComponent(
                organization_id=organization.id,
                bom_id=bom.id,
                input_product_id=material.id,
                quantity=10,
                unit="g",
                scrap_pct=0,
            )
        )
        lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=material.id,
            lot_code="MAT-LOT-START",
            location_code="VAULT",
            status="available",
        )
        order = ProductionOrder(
            organization_id=organization.id,
            facility_id=facility.id,
            order_number=f"RUN-{status.upper()}",
            work_type="internal",
            product_name=finished.name,
            sku=finished.sku,
            product_format="test",
            requested_units=10,
            priority="normal",
            status=status,
            created_by="seed",
            updated_by="seed",
        )
        session.add_all([lot, order])
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=20,
                unit="g",
                actor="seed",
            )
        )
        session.commit()
        return engine, organization.id, facility.id, order.id, lot.id


def _started_count(session: Session, organization_id: str, facility_id: str, order_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(ProductionRunEvent.id)).where(
                ProductionRunEvent.organization_id == organization_id,
                ProductionRunEvent.facility_id == facility_id,
                ProductionRunEvent.production_order_id == order_id,
                ProductionRunEvent.event_type == "started",
            )
        )
        or 0
    )


def test_reservation_stays_planning_and_first_consumption_starts_run_once():
    engine, organization_id, facility_id, order_id, lot_id = _fixture(status="draft")
    service = ProductionRun360MutationService(engine)

    reserve = service.preview(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="reserve_materials",
        payload={},
    )
    assert reserve["blocker_count"] == 0
    service.commit(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="reserve_materials",
        payload={},
        preview_key=reserve["preview_key"],
        actor="planner",
    )
    with Session(engine) as session:
        assert session.get(ProductionOrder, order_id).status == "draft"
        assert _started_count(session, organization_id, facility_id, order_id) == 0

    first_payload = {"materials": [{"lot_id": lot_id, "quantity": 4, "unit": "g"}]}
    first = service.preview(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="consume_materials",
        payload=first_payload,
    )
    assert first["blocker_count"] == 0
    service.commit(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="consume_materials",
        payload=first_payload,
        preview_key=first["preview_key"],
        actor="operator",
    )
    with Session(engine) as session:
        assert session.get(ProductionOrder, order_id).status == "in_progress"
        assert _started_count(session, organization_id, facility_id, order_id) == 1

    second_payload = {"materials": [{"lot_id": lot_id, "quantity": 2, "unit": "g"}]}
    second = service.preview(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="consume_materials",
        payload=second_payload,
    )
    assert second["blocker_count"] == 0
    service.commit(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="consume_materials",
        payload=second_payload,
        preview_key=second["preview_key"],
        actor="operator",
    )
    with Session(engine) as session:
        assert session.get(ProductionOrder, order_id).status == "in_progress"
        assert _started_count(session, organization_id, facility_id, order_id) == 1
        balance = session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == lot_id
            )
        )
        assert float(balance or 0) == 14.0


def test_scheduled_run_starts_when_first_physical_consumption_posts():
    engine, organization_id, facility_id, order_id, lot_id = _fixture(status="scheduled")
    service = ProductionIntegrityMutationService(engine)
    payload = {"materials": [{"lot_id": lot_id, "quantity": 1, "unit": "g"}]}
    preview = service.preview(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="consume_materials",
        payload=payload,
    )
    assert preview["blocker_count"] == 0
    assert preview["details"]["starts_run"] is True
    service.commit(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type="consume_materials",
        payload=payload,
        preview_key=preview["preview_key"],
        actor="operator",
    )
    with Session(engine) as session:
        assert session.get(ProductionOrder, order_id).status == "in_progress"
        assert _started_count(session, organization_id, facility_id, order_id) == 1


@pytest.mark.parametrize("status", ["on_hold", "complete", "cancelled"])
def test_held_or_closed_run_cannot_consume_physical_material(status: str):
    engine, organization_id, facility_id, order_id, lot_id = _fixture(status=status)
    service = ProductionIntegrityMutationService(engine)
    with pytest.raises(ValueError, match="Held, completed, and cancelled"):
        service.preview(
            organization_id=organization_id,
            facility_id=facility_id,
            order_id=order_id,
            action_type="consume_materials",
            payload={"materials": [{"lot_id": lot_id, "quantity": 1, "unit": "g"}]},
        )
