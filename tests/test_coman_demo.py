from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from modules.coman.demo_data import (
    DEMO_ORGANIZATION_SLUG,
    ensure_coman_demo_dataset,
    reset_coman_demo_dataset,
)
from modules.coman.models import (
    AuditEvent,
    Base,
    Customer,
    Facility,
    FacilityMachine,
    InventoryLot,
    Organization,
    Product,
    ProductionActual,
    ProductionOrder,
)
from services.demo_data import build_demo_payload


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _count(session: Session, model, organization_id: str | None = None) -> int:
    statement = select(func.count()).select_from(model)
    if organization_id is not None and hasattr(model, "organization_id"):
        statement = statement.where(model.organization_id == organization_id)
    return int(session.scalar(statement) or 0)


def test_durable_demo_seed_is_complete_idempotent_and_force_refreshable():
    engine = _engine()
    state: dict = {}
    payload = build_demo_payload(date(2026, 7, 22), scale="small")

    first = ensure_coman_demo_dataset(
        state=state,
        actor="seed-test",
        payload=payload,
        engine=engine,
    )

    assert first["seeded"] is True
    assert first["already_present"] is False
    assert first["products"] > 0
    assert first["orders"] > 0
    assert state["active_organization_id"] == first["organization_id"]
    assert state["active_facility_id"] == first["facility_id"]

    with Session(engine) as session:
        organization = session.scalar(
            select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG)
        )
        assert organization is not None
        assert _count(session, Customer, organization.id) == 3
        assert _count(session, Product, organization.id) == first["products"]
        assert _count(session, ProductionOrder, organization.id) == first["orders"]
        assert _count(session, ProductionActual, organization.id) >= 1
        assert _count(session, InventoryLot, organization.id) >= 1
        assert _count(session, AuditEvent, organization.id) == 1

    second = ensure_coman_demo_dataset(
        state=state,
        actor="seed-test",
        payload=payload,
        engine=engine,
    )
    assert second["seeded"] is False
    assert second["already_present"] is True
    assert second["organization_id"] == first["organization_id"]

    incident_payload = build_demo_payload(
        date(2026, 7, 23),
        scale="small",
        problems={"machine_downtime", "late_po"},
    )
    refreshed = ensure_coman_demo_dataset(
        state=state,
        actor="incident-test",
        payload=incident_payload,
        force=True,
        engine=engine,
    )

    assert refreshed["seeded"] is True
    assert refreshed["organization_id"] == first["organization_id"]
    with Session(engine) as session:
        packaging_line = session.scalar(
            select(FacilityMachine).where(
                FacilityMachine.organization_id == refreshed["organization_id"],
                FacilityMachine.asset_code == "PKG-01",
            )
        )
        assert packaging_line is not None
        assert packaging_line.active is False
        assert _count(session, Product, refreshed["organization_id"]) == refreshed["products"]
        assert _count(session, AuditEvent, refreshed["organization_id"]) == 1
        late_order = session.scalar(
            select(ProductionOrder).where(
                ProductionOrder.organization_id == refreshed["organization_id"],
                ProductionOrder.priority == "urgent",
            )
        )
        assert late_order is not None


def test_reset_removes_only_the_demo_tenant_and_is_idempotent():
    engine = _engine()
    with Session(engine) as session:
        permanent = Organization(name="Permanent Tenant", slug="permanent-tenant", active=True)
        session.add(permanent)
        session.commit()
        permanent_id = permanent.id

    payload = build_demo_payload(date(2026, 7, 22), scale="small")
    seeded = ensure_coman_demo_dataset(
        state={},
        actor="seed-test",
        payload=payload,
        engine=engine,
    )

    result = reset_coman_demo_dataset(engine=engine)
    assert result == {"deleted": True}

    with Session(engine) as session:
        assert session.get(Organization, permanent_id) is not None
        assert session.get(Organization, seeded["organization_id"]) is None
        assert session.get(Facility, seeded["facility_id"]) is None
        assert _count(session, Product, seeded["organization_id"]) == 0
        assert _count(session, ProductionOrder, seeded["organization_id"]) == 0
        assert _count(session, AuditEvent, seeded["organization_id"]) == 0

    assert reset_coman_demo_dataset(engine=engine) == {
        "deleted": False,
        "reason": "not_found",
    }
