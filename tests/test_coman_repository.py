from __future__ import annotations

from sqlalchemy import create_engine, func, select

from modules.coman.models import AuditEvent, Base, MachineModel
from modules.coman.planning import estimate_hand_labor_job, estimate_machine_job
from modules.coman.repository import ComanRepository


def _repository() -> tuple[ComanRepository, object]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return ComanRepository(engine), engine


def test_internal_order_is_persisted_and_audited():
    repository, engine = _repository()
    organization = repository.create_organization("DoobieLogic")
    facility = repository.create_facility(organization.id, "Main Production", "MAIN")

    order = repository.create_production_order(
        organization_id=organization.id,
        facility_id=facility.id,
        order_number="COM-000001",
        work_type="internal",
        product_name="House Flower 3.5g",
        product_format="pouched flower",
        requested_units=10000,
        actor="admin",
    )

    orders = repository.list_production_orders(organization.id, facility.id)
    assert [saved.id for saved in orders] == [order.id]
    assert orders[0].status == "draft"
    with engine.connect() as connection:
        audit_count = connection.scalar(select(func.count()).select_from(AuditEvent))
    assert audit_count == 1


def test_external_order_requires_customer():
    repository, _ = _repository()
    organization = repository.create_organization("DoobieLogic")
    facility = repository.create_facility(organization.id, "Main Production", "MAIN")

    try:
        repository.create_production_order(
            organization_id=organization.id,
            facility_id=facility.id,
            order_number="COM-000002",
            work_type="external",
            product_name="Client Pre-Roll 1g",
            product_format="pre-roll",
            requested_units=5000,
            actor="admin",
        )
    except ValueError as exc:
        assert "require a customer" in str(exc)
    else:
        raise AssertionError("External orders without customers must be rejected.")


def test_customers_are_listed_only_for_their_organization():
    repository, _ = _repository()
    first = repository.create_organization("First Company")
    second = repository.create_organization("Second Company")
    repository.create_customer(first.id, "Zeta Farms")
    repository.create_customer(first.id, "Alpha Growers")
    repository.create_customer(second.id, "Hidden Customer")

    customers = repository.list_customers(first.id)

    assert [customer.name for customer in customers] == ["Alpha Growers", "Zeta Farms"]


def test_external_order_cannot_use_another_organizations_customer():
    repository, _ = _repository()
    first = repository.create_organization("First Company")
    second = repository.create_organization("Second Company")
    facility = repository.create_facility(first.id, "First Facility", "FIRST")
    other_customer = repository.create_customer(second.id, "Other Customer")

    try:
        repository.create_production_order(
            organization_id=first.id,
            facility_id=facility.id,
            customer_id=other_customer.id,
            order_number="COM-000003",
            work_type="external",
            product_name="Client Flower",
            product_format="jarred flower",
            requested_units=1000,
            actor="admin",
        )
    except ValueError as exc:
        assert "Customer does not belong" in str(exc)
    else:
        raise AssertionError("Cross-organization customer access must be rejected.")


def test_facility_machine_is_scoped_and_capacity_is_calculated():
    repository, engine = _repository()
    organization = repository.create_organization("DoobieLogic")
    facility = repository.create_facility(organization.id, "Main Production", "MAIN")
    with engine.begin() as connection:
        connection.execute(
            MachineModel.__table__.insert(),
            {
                "manufacturer": "Test Make",
                "model": "Test Model",
                "category": "pre-roll",
                "published_max_rate": 100,
            },
        )
    model = repository.list_machine_models()[0]
    machine = repository.create_facility_machine(
        organization_id=organization.id,
        facility_id=facility.id,
        machine_model_id=model.id,
        asset_code="PR-01",
        display_name="Pre-roll Line 1",
        effective_rate=500,
        preferred_crew_size=3,
        setup_minutes=30,
        cleanup_minutes=30,
        actor="admin",
    )

    assert [item.id for item in repository.list_facility_machines(organization.id, facility.id)] == [machine.id]
    estimate = estimate_machine_job(4000, 500, 3, 30, 30, 8)
    assert estimate == {"run_hours": 8.0, "elapsed_hours": 9.0, "labor_hours": 27.0, "shifts": 2}


def test_required_hand_labor_area_and_downstream_estimate():
    repository, _ = _repository()
    organization = repository.create_organization("DoobieLogic")
    facility = repository.create_facility(organization.id, "Main Production", "MAIN")
    area = repository.ensure_primary_hand_labor_area(organization.id, facility.id)
    updated = repository.update_hand_labor_area(area.id, organization_id=organization.id, facility_id=facility.id, default_crew_size=4, sticker_units_per_person_hour=100, case_pack_units_per_person_hour=200, final_cases_per_person_hour=10, setup_minutes=30, cleanup_minutes=30, actor="admin")
    assert updated.name == "Primary Hand Labor Area"
    estimate = estimate_hand_labor_job(4000, 4, 100, 200, 10, 100, 30, 30)
    assert estimate["cases"] == 40
    assert estimate["sticker_hours"] == 10
    assert estimate["case_pack_hours"] == 5
    assert estimate["final_case_hours"] == 1
    assert estimate["elapsed_hours"] == 17
    assert estimate["labor_hours"] == 68
    assert estimate["bottleneck"] == "Stickering"


def test_order_status_and_duplicate_are_persisted():
    repository, _ = _repository()
    organization = repository.create_organization("DoobieLogic")
    facility = repository.create_facility(organization.id, "Main Production", "MAIN")
    order = repository.create_production_order(organization_id=organization.id, facility_id=facility.id, order_number="COM-1", work_type="internal", product_name="House Pre-roll", product_format="pre-roll", requested_units=1000, actor="admin")
    updated = repository.update_production_order_status(order.id, organization_id=organization.id, facility_id=facility.id, status="scheduled", actor="planner")
    duplicate = repository.duplicate_production_order(order.id, organization_id=organization.id, facility_id=facility.id, new_order_number="COM-2", actor="planner")
    assert updated.status == "scheduled"
    assert duplicate.order_number == "COM-2"
    assert duplicate.requested_units == 1000
