from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.routers.coman_parity import workspace as production_workspace
from backend.app.services.enterprise_control_fast import organization_secondary_metrics
from modules.coman.models import (
    Base,
    CrewAvailability,
    Customer,
    Facility,
    FacilityMachine,
    HandLaborArea,
    InventoryLot,
    InventoryTransaction,
    MachineModel,
    MaterialReservation,
    Organization,
    Product,
    ProductionActual,
    ProductionOrder,
)
from modules.operational_moats.models import LabelReview
from modules.traceability.models import TraceabilityTransaction


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _count_selects(engine):
    statements: list[str] = []

    def listener(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", listener)
    return statements, listener


def _seed_production_volume(engine):
    """Seed a busy single facility without timing setup work."""
    with Session(engine) as session:
        organization = Organization(name="Volume Production Org", slug="volume-production-org")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Volume Production",
            code="VOL-PROD",
            production_enabled=True,
            retail_enabled=False,
        )
        session.add(facility)
        session.flush()

        products = [
            Product(
                organization_id=organization.id,
                sku=f"PERF-{index:03d}",
                name=f"Performance Product {index:03d}",
                item_type="cannabis" if index < 20 else "finished_good",
                base_unit="g" if index < 20 else "each",
                unit_cost=1.5 + (index % 10) * 0.1,
            )
            for index in range(60)
        ]
        customers = [
            Customer(
                organization_id=organization.id,
                name=f"Performance Customer {index:03d}",
                license_or_registration=f"LIC-{index:05d}",
                contact_name=f"Customer {index}",
                contact_email=f"customer-{index}@example.test",
            )
            for index in range(80)
        ]
        machine_models = [
            MachineModel(
                manufacturer="Performance Machines",
                model=f"PM-{index:02d}",
                category="flower_packaging",
                published_max_rate=500 + index * 25,
                rate_unit="units/hour",
                published_min_operators=1,
                planning_utilization_pct=65,
            )
            for index in range(8)
        ]
        session.add_all(products + customers + machine_models)
        session.flush()
        session.add_all(
            [
                FacilityMachine(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    machine_model_id=model.id,
                    asset_code=f"ASSET-{index:02d}",
                    display_name=f"Performance Machine {index:02d}",
                    effective_rate=400 + index * 20,
                    preferred_crew_size=3,
                )
                for index, model in enumerate(machine_models)
            ]
        )
        session.add(
            HandLaborArea(
                organization_id=organization.id,
                facility_id=facility.id,
                name="Primary Hand Labor Area",
                default_crew_size=8,
                sticker_units_per_person_hour=350,
                case_pack_units_per_person_hour=250,
                final_cases_per_person_hour=80,
            )
        )

        orders = [
            ProductionOrder(
                organization_id=organization.id,
                facility_id=facility.id,
                customer_id=customers[index % len(customers)].id if index % 5 == 0 else None,
                order_number=f"PERF-RUN-{index:05d}",
                work_type="external" if index % 5 == 0 else "internal",
                product_name=products[index % len(products)].name,
                sku=products[index % len(products)].sku,
                product_format="finished good",
                requested_units=100 + (index % 20) * 10,
                priority="high" if index % 11 == 0 else "normal",
                status="complete" if index < 300 else "scheduled",
                created_by="performance-test",
                updated_by="performance-test",
            )
            for index in range(500)
        ]
        lots = [
            InventoryLot(
                organization_id=organization.id,
                facility_id=facility.id,
                product_id=products[index % len(products)].id,
                lot_code=f"PERF-LOT-{index:05d}",
                compliance_package_id=f"1A406PERF{index:08d}",
                location_code=f"ROOM-{index % 12:02d}",
                status="available",
            )
            for index in range(1000)
        ]
        session.add_all(orders + lots)
        session.flush()

        transaction_rows = []
        for lot in lots:
            transaction_rows.extend(
                [
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=lot.id,
                        transaction_type="receipt",
                        quantity_delta=100.0,
                        unit="g",
                        actor="performance-test",
                    ),
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=lot.id,
                        transaction_type="adjustment",
                        quantity_delta=-1.0,
                        unit="g",
                        actor="performance-test",
                    ),
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=lot.id,
                        transaction_type="adjustment",
                        quantity_delta=0.5,
                        unit="g",
                        actor="performance-test",
                    ),
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=lot.id,
                        transaction_type="adjustment",
                        quantity_delta=-0.25,
                        unit="g",
                        actor="performance-test",
                    ),
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=lot.id,
                        transaction_type="adjustment",
                        quantity_delta=0.25,
                        unit="g",
                        actor="performance-test",
                    ),
                ]
            )
        session.add_all(transaction_rows)
        session.add_all(
            [
                MaterialReservation(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    production_order_id=orders[index].id,
                    lot_id=lots[index].id,
                    quantity=5.0,
                    unit="g",
                    status="reserved",
                    reserved_by="performance-test",
                )
                for index in range(500)
            ]
        )
        completed_at = datetime.now(timezone.utc)
        session.add_all(
            [
                ProductionActual(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    production_order_id=orders[index].id,
                    actual_units=orders[index].requested_units - 2,
                    scrap_units=2,
                    rework_units=0,
                    actual_machine_hours=2.0,
                    actual_labor_hours=6.0,
                    completed_at=completed_at,
                    recorded_by="performance-test",
                )
                for index in range(300)
            ]
        )
        session.add_all(
            [
                CrewAvailability(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    work_date=date.today() + timedelta(days=index),
                    shift_name="Day",
                    available_people=12,
                    shift_hours=8.0,
                    updated_by="performance-test",
                )
                for index in range(60)
            ]
        )
        session.commit()
        return organization.id, facility.id


def test_production_workspace_stays_bounded_at_realistic_volume() -> None:
    engine = _engine()
    organization_id, facility_id = _seed_production_volume(engine)
    context = RequestContext(
        user_id="performance-test",
        organization_id=organization_id,
        facility_id=facility_id,
        role="dev",
    )
    selects, listener = _count_selects(engine)
    started = perf_counter()
    try:
        payload = production_workspace(context=context, engine=engine)
    finally:
        elapsed = perf_counter() - started
        event.remove(engine, "before_cursor_execute", listener)

    encoded_size = len(json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8"))
    assert len(selects) <= 12, f"Production workspace used {len(selects)} SELECTs at realistic volume"
    assert elapsed < 3.0, f"Production workspace took {elapsed:.3f}s at realistic volume"
    assert encoded_size < 4_000_000, f"Production workspace payload grew to {encoded_size} bytes"
    assert len(payload["orders"]) == 500
    assert len(payload["lots"]) == 1000
    assert len(payload["transactions"]) == 250
    assert len(payload["reservations"]) == 500
    assert len(payload["actuals"]) == 300


def _seed_enterprise_history(engine):
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        organization = Organization(name="Volume Enterprise Org", slug="volume-enterprise-org")
        session.add(organization)
        session.flush()
        facilities = [
            Facility(
                organization_id=organization.id,
                name=f"Enterprise Facility {index}",
                code=f"ENT-{index}",
                production_enabled=True,
            )
            for index in range(3)
        ]
        session.add_all(facilities)
        session.flush()
        for facility in facilities:
            session.add_all(
                [
                    TraceabilityTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        provider="metrc",
                        operation_type="package_adjust",
                        entity_type="package",
                        entity_id=f"{facility.id}-pkg-{index}",
                        idempotency_key=f"{facility.id}-trace-{index}",
                        status="accepted" if index < 1000 else "rejected",
                        requested_by="performance-test",
                        requested_at=now - timedelta(seconds=index),
                    )
                    for index in range(1105)
                ]
            )
            session.add_all(
                [
                    LabelReview(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        status=("fail" if index < 10 or index >= 100 else "pass"),
                        reviewed_by="performance-test",
                        reviewed_at=now - timedelta(seconds=index),
                    )
                    for index in range(150)
                ]
            )
        session.commit()
        return organization.id, [facility.id for facility in facilities]


def test_enterprise_secondary_summary_is_fixed_query_and_bounded_by_legacy_windows() -> None:
    engine = _engine()
    organization_id, facility_ids = _seed_enterprise_history(engine)
    selects, listener = _count_selects(engine)
    started = perf_counter()
    try:
        payload = organization_secondary_metrics(engine, organization_id)
    finally:
        elapsed = perf_counter() - started
        event.remove(engine, "before_cursor_execute", listener)

    assert len(selects) == 4, f"Enterprise secondary projection used {len(selects)} SELECTs"
    assert elapsed < 3.0, f"Enterprise secondary projection took {elapsed:.3f}s"
    for facility_id in facility_ids:
        trace = payload["traceability"][facility_id]
        compliance = payload["compliance"][facility_id]
        assert trace["total"] == 1000
        assert trace.get("accepted") == 1000
        assert trace.get("rejected", 0) == 0
        assert trace["needs_reconciliation"] == 0
        assert compliance["label_failures"] == 10
