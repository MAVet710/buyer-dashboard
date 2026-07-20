from __future__ import annotations

from sqlalchemy import create_engine, func, select

from modules.coman.models import AuditEvent, Base
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
