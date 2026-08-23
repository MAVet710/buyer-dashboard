from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.main import app
from backend.app.routers.admin_facilities import FacilityUpdate, update_facility
from modules.coman.models import AuditEvent, Base, Facility, Organization


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(id="org-1", name="Medicine Man", slug="medicine-man")
        facility = Facility(
            id="facility-retail",
            organization_id=organization.id,
            name="Taunton",
            code="TAUNTON",
            retail_enabled=True,
            production_enabled=True,
            commercial_enabled=True,
        )
        other = Facility(
            id="facility-other",
            organization_id=organization.id,
            name="Other",
            code="OTHER",
            retail_enabled=True,
            production_enabled=False,
        )
        session.add_all((organization, facility, other))
        session.commit()
    return engine


def _payload(**overrides):
    values = {
        "name": "Taunton Retail",
        "code": "TAUNTON",
        "timezone_name": "America/New_York",
        "license_number": "MR283261",
        "license_type": "Marijuana Retailer",
        "retail_enabled": True,
        "production_enabled": False,
        "cultivation_enabled": False,
        "commercial_enabled": True,
        "active": True,
    }
    values.update(overrides)
    return FacilityUpdate(**values)


def test_dev_can_correct_license_and_remove_incorrect_production_capability():
    engine = _engine()
    context = RequestContext("dev-user", "org-dev", "sandbox-facility", "dev")

    result = update_facility("facility-retail", _payload(), context=context, engine=engine)

    assert result["license_number"] == "MR283261"
    assert result["license_type"] == "Marijuana Retailer"
    assert result["retail_enabled"] is True
    assert result["production_enabled"] is False
    with Session(engine) as session:
        row = session.get(Facility, "facility-retail")
        assert row.name == "Taunton Retail"
        assert row.production_enabled is False
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "facility",
                AuditEvent.entity_id == "facility-retail",
                AuditEvent.action == "facility_context_updated",
            )
        )
        assert event is not None
        assert event.actor == "dev-user"
        assert "license_number" in event.changes_json
        assert "production_enabled" in event.changes_json


def test_non_dev_cannot_edit_facility_license_context():
    engine = _engine()
    context = RequestContext("admin-user", "org-1", "facility-retail", "admin")

    try:
        update_facility("facility-retail", _payload(), context=context, engine=engine)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Non-DEV facility update unexpectedly succeeded")


def test_duplicate_facility_code_is_rejected_within_organization():
    engine = _engine()
    context = RequestContext("dev-user", "org-dev", "sandbox-facility", "dev")

    try:
        update_facility("facility-retail", _payload(code="OTHER"), context=context, engine=engine)
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("Duplicate facility code unexpectedly succeeded")


def test_facility_context_update_route_is_registered():
    assert any(getattr(route, "name", "") == "update_facility" for route in app.routes)
