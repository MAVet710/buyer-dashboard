import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.regulatory_actions import RegulatoryActionProposalService
from modules.coman.models import (
    Base,
    Facility,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Organization,
    Product,
    ProductBom,
    ProductionOrder,
    utc_now,
)
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.production_erp.integrity_mutations import ProductionIntegrityMutationService
from modules.production_erp.models import ProductionBomStandard, ProductionRunOutput


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _scope(session: Session, slug: str):
    organization = Organization(name=slug, slug=slug)
    session.add(organization)
    session.flush()
    facility = Facility(
        organization_id=organization.id,
        name=f"{slug} facility",
        code=slug.upper()[:16],
        retail_enabled=False,
        production_enabled=True,
    )
    material = Product(
        organization_id=organization.id,
        sku=f"{slug}-MAT",
        name=f"{slug} material",
        item_type="cannabis",
        base_unit="g",
    )
    finished = Product(
        organization_id=organization.id,
        sku=f"{slug}-FG",
        name=f"{slug} finished",
        item_type="finished_good",
        base_unit="unit",
    )
    session.add_all([facility, material, finished])
    session.flush()
    return organization, facility, material, finished


def _lot(session: Session, organization, facility, product, code: str, quantity: float = 0):
    lot = InventoryLot(
        organization_id=organization.id,
        facility_id=facility.id,
        product_id=product.id,
        lot_code=code,
        status="available",
        compliance_package_id=f"PKG-{code}",
    )
    session.add(lot)
    session.flush()
    if quantity:
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=quantity,
                unit=product.base_unit,
                actor="seed",
            )
        )
        session.flush()
    return lot


def _order(session: Session, organization, facility, finished, number: str, status: str = "in_progress"):
    order = ProductionOrder(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number=number,
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
    session.add(order)
    session.flush()
    return order


def test_inventory_transaction_rejects_cross_facility_lot_scope():
    engine = _engine()
    with Session(engine) as session:
        org_a, fac_a, mat_a, _ = _scope(session, "scope-a")
        org_b, fac_b, _, _ = _scope(session, "scope-b")
        lot_a = _lot(session, org_a, fac_a, mat_a, "A-LOT", 10)
        session.commit()

        session.add(
            InventoryTransaction(
                organization_id=org_b.id,
                facility_id=fac_b.id,
                lot_id=lot_a.id,
                transaction_type="adjustment",
                quantity_delta=1,
                unit="g",
                actor="bad-write",
            )
        )
        with pytest.raises(ValueError, match="organization"):
            session.commit()


def test_material_reservation_rejects_cross_scope_parent():
    engine = _engine()
    with Session(engine) as session:
        org_a, fac_a, mat_a, fg_a = _scope(session, "reserve-a")
        org_b, fac_b, mat_b, _ = _scope(session, "reserve-b")
        order_a = _order(session, org_a, fac_a, fg_a, "RUN-A")
        lot_b = _lot(session, org_b, fac_b, mat_b, "B-LOT", 10)
        session.commit()

        session.add(
            MaterialReservation(
                organization_id=org_a.id,
                facility_id=fac_a.id,
                production_order_id=order_a.id,
                lot_id=lot_b.id,
                quantity=1,
                unit="g",
                status="reserved",
                reserved_by="bad-write",
            )
        )
        with pytest.raises(ValueError, match="Material reservation lot"):
            session.commit()


def test_inventory_adjustment_cannot_reduce_below_active_claims():
    engine = _engine()
    with Session(engine) as session:
        organization, facility, material, finished = _scope(session, "claims")
        lot = _lot(session, organization, facility, material, "CLAIM-LOT", 100)
        order = _order(session, organization, facility, finished, "RUN-CLAIM")
        session.add(
            MaterialReservation(
                organization_id=organization.id,
                facility_id=facility.id,
                production_order_id=order.id,
                lot_id=lot.id,
                quantity=60,
                unit="g",
                status="reserved",
                reserved_by="planner",
            )
        )
        session.commit()

        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="inventory_adjustment",
                quantity_delta=-50,
                unit="g",
                actor="operator",
            )
        )
        with pytest.raises(ValueError, match="below active Production/Wholesale commitments"):
            session.commit()


def test_inventory_availability_preserves_negative_ledger_evidence():
    engine = _engine()
    with Session(engine) as session:
        organization, facility, material, _ = _scope(session, "negative")
        lot = _lot(session, organization, facility, material, "NEG-LOT", 0)
        session.commit()

        # Core insert intentionally bypasses ORM guards to simulate legacy/corrupt data.
        session.execute(
            InventoryTransaction.__table__.insert().values(
                id=str(uuid.uuid4()),
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="legacy_bad_adjustment",
                quantity_delta=-5.0,
                unit="g",
                reason="legacy drift",
                reference="legacy",
                actor="legacy",
                occurred_at=utc_now(),
            )
        )
        session.commit()
        snapshot = InventoryAvailabilityService.build(session, organization.id, facility.id)
        assert snapshot["by_lot"][lot.id]["on_hand"] == -5.0
        assert snapshot["by_lot"][lot.id]["available"] == 0.0
        assert any(
            row["code"] == "negative_physical_balance" and row["lot_id"] == lot.id
            for row in snapshot["integrity_issues"]
        )


def test_closed_production_order_reservation_is_reported_but_not_counted():
    engine = _engine()
    with Session(engine) as session:
        organization, facility, material, finished = _scope(session, "stale")
        lot = _lot(session, organization, facility, material, "STALE-LOT", 100)
        order = _order(session, organization, facility, finished, "RUN-STALE")
        reservation = MaterialReservation(
            organization_id=organization.id,
            facility_id=facility.id,
            production_order_id=order.id,
            lot_id=lot.id,
            quantity=70,
            unit="g",
            status="reserved",
            reserved_by="planner",
        )
        session.add(reservation)
        session.commit()
        order.status = "complete"
        session.commit()

        snapshot = InventoryAvailabilityService.build(session, organization.id, facility.id)
        assert snapshot["by_lot"][lot.id]["production_reserved"] == 0.0
        assert snapshot["by_lot"][lot.id]["available"] == 100.0
        assert any(row["code"] == "stale_production_reservation" for row in snapshot["integrity_issues"])


def test_production_completion_requires_in_progress_and_physical_disposition():
    engine = _engine()
    with Session(engine) as session:
        organization, facility, _, finished = _scope(session, "closeout")
        draft = _order(session, organization, facility, finished, "RUN-DRAFT", status="draft")
        active = _order(session, organization, facility, finished, "RUN-ACTIVE", status="in_progress")
        session.commit()
        org_id, facility_id, draft_id, active_id = organization.id, facility.id, draft.id, active.id

    service = ProductionIntegrityMutationService(engine)
    with pytest.raises(ValueError, match="in progress"):
        service.preview(
            organization_id=org_id,
            facility_id=facility_id,
            order_id=draft_id,
            action_type="run_event",
            payload={"event_type": "completed"},
        )

    preview = service.preview(
        organization_id=org_id,
        facility_id=facility_id,
        order_id=active_id,
        action_type="run_event",
        payload={"event_type": "completed"},
    )
    assert preview["blocker_count"] >= 1
    assert any("no measured output or waste disposition" in row["message"] for row in preview["warnings"])
    with pytest.raises(ValueError, match="blockers"):
        service.commit(
            organization_id=org_id,
            facility_id=facility_id,
            order_id=active_id,
            action_type="run_event",
            payload={"event_type": "completed"},
            preview_key=preview["preview_key"],
            actor="operator",
        )


def test_required_qa_release_requires_document_reference():
    engine = _engine()
    with Session(engine) as session:
        organization, facility, _, finished = _scope(session, "qa-proof")
        order = _order(session, organization, facility, finished, "RUN-QA")
        bom = ProductBom(
            organization_id=organization.id,
            output_product_id=finished.id,
            version=1,
            output_quantity=1,
            expected_loss_pct=0,
            active=True,
        )
        session.add(bom)
        session.flush()
        session.add(
            ProductionBomStandard(
                organization_id=organization.id,
                bom_id=bom.id,
                standard_labor_hours=0,
                standard_machine_hours=0,
                standard_cycle_hours=0,
                resource_category="test",
                qa_required=True,
                compliance_checkpoint="COA required",
                created_by="seed",
                updated_by="seed",
            )
        )
        lot = _lot(session, organization, facility, finished, "QA-LOT", 1)
        output = ProductionRunOutput(
            organization_id=organization.id,
            facility_id=facility.id,
            production_order_id=order.id,
            product_id=finished.id,
            lot_id=lot.id,
            position=1,
            label="Finished",
            planned_quantity=1,
            actual_quantity=1,
            unit="unit",
            status="quarantine",
            created_by="seed",
        )
        session.add(output)
        session.commit()
        ids = organization.id, facility.id, order.id, output.id

    service = ProductionIntegrityMutationService(engine)
    payload = {
        "event_type": "release",
        "result": "passed",
        "output_id": ids[3],
        "document_reference": "",
    }
    preview = service.preview(
        organization_id=ids[0],
        facility_id=ids[1],
        order_id=ids[2],
        action_type="qa_decision",
        payload=payload,
    )
    assert preview["blocker_count"] >= 1
    assert any("requires QA evidence" in row["message"] for row in preview["warnings"])


def test_regulatory_package_finish_candidates_exclude_claimed_zero_balance_package():
    engine = _engine()
    with Session(engine) as session:
        organization, facility, material, finished = _scope(session, "regulatory")
        lot = _lot(session, organization, facility, material, "REG-LOT", 0)
        order = _order(session, organization, facility, finished, "RUN-REG")
        session.add(
            MaterialReservation(
                organization_id=organization.id,
                facility_id=facility.id,
                production_order_id=order.id,
                lot_id=lot.id,
                quantity=1,
                unit="g",
                status="reserved",
                reserved_by="planner",
            )
        )
        session.commit()
        org_id, facility_id = organization.id, facility.id

    candidates = RegulatoryActionProposalService(engine).package_finish_candidates(org_id, facility_id)
    assert candidates == []
