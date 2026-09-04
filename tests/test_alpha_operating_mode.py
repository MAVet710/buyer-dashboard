from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.services.metrc_context import resolve_metrc_context
from modules.alpha_mode import AlphaOperatingMode, AlphaOperatingModeService
from modules.coman.models import AuditEvent, Base, Facility, Organization, utc_now
from modules.regulatory.models import RegulatoryFacilityMapping


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    with Session(engine) as session, session.begin():
        organization = Organization(name="Alpha Operator", slug="alpha-operator")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Alpha Facility",
            code="ALPHA-1",
            cultivation_enabled=True,
            production_enabled=True,
            retail_enabled=True,
        )
        session.add(facility)
        session.flush()
        return organization.id, facility.id


def _mapping(engine, organization_id: str, facility_id: str, *, verified: bool = True):
    with Session(engine) as session, session.begin():
        session.add(
            RegulatoryFacilityMapping(
                organization_id=organization_id,
                facility_id=facility_id,
                provider="metrc",
                jurisdiction_code="MA",
                license_number="LIC-ALPHA",
                provider_facility_id="455",
                environment="sandbox",
                active=True,
                verified_at=utc_now() if verified else None,
                verified_by="admin" if verified else "",
            )
        )


def test_new_unmapped_facility_defaults_to_doobielogic_sandbox():
    engine = _engine()
    organization_id, facility_id = _scope(engine)

    state = AlphaOperatingModeService(engine).current(organization_id, facility_id)

    assert state.effective_mode == "doobielogic_sandbox"
    assert state.selected_mode == "doobielogic_sandbox"
    assert state.explicit is False
    assert state.source == "default_local_alpha"
    assert state.metrc_enabled is False


def test_unverified_mapping_does_not_auto_enable_metrc():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    _mapping(engine, organization_id, facility_id, verified=False)

    state = AlphaOperatingModeService(engine).current(organization_id, facility_id)

    assert state.effective_mode == "doobielogic_sandbox"
    assert state.metrc_sandbox_mapping_available is False


def test_existing_verified_sandbox_mapping_preserves_metrc_behavior():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    _mapping(engine, organization_id, facility_id)

    state = AlphaOperatingModeService(engine).current(organization_id, facility_id)

    assert state.effective_mode == "metrc_sandbox"
    assert state.explicit is False
    assert state.source == "existing_metrc_mapping"
    assert state.metrc_enabled is True


def test_explicit_doobielogic_sandbox_overrides_existing_metrc_mapping():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    _mapping(engine, organization_id, facility_id)
    service = AlphaOperatingModeService(engine)

    state = service.set_mode(
        organization_id,
        facility_id,
        mode="doobielogic_sandbox",
        actor="admin-user",
    )

    assert state.effective_mode == "doobielogic_sandbox"
    assert state.explicit is True
    assert state.metrc_sandbox_mapping_available is True
    with Session(engine) as session:
        row = session.scalar(select(AlphaOperatingMode).where(AlphaOperatingMode.facility_id == facility_id))
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.facility_id == facility_id,
                AuditEvent.entity_type == "alpha_operating_mode",
                AuditEvent.action == "operating_mode_changed",
            )
        )
    assert row is not None and row.mode == "doobielogic_sandbox"
    assert audit is not None


def test_metrc_sandbox_can_be_selected_before_credentials_or_mapping_exist():
    engine = _engine()
    organization_id, facility_id = _scope(engine)

    state = AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="metrc_sandbox",
        actor="admin-user",
    )

    assert state.effective_mode == "metrc_sandbox"
    assert state.explicit is True
    assert state.metrc_sandbox_mapping_available is False
    assert state.metrc_enabled is True


def test_doobielogic_sandbox_disables_metrc_context_before_credentials():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="doobielogic_sandbox",
        actor="admin-user",
    )
    context = RequestContext(
        user_id="operator",
        organization_id=organization_id,
        facility_id=facility_id,
        role="admin",
    )

    _, metrc = resolve_metrc_context(engine, Settings(), context)

    assert metrc.configured is False
    assert metrc.environment == "sandbox"
    assert metrc.status == "disabled_by_alpha_mode"
    assert "DoobieLogic Sandbox is active" in metrc.message


def test_mode_is_tenant_and_facility_scoped():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    service = AlphaOperatingModeService(engine)
    service.set_mode(organization_id, facility_id, mode="metrc_sandbox", actor="admin-user")

    with Session(engine) as session, session.begin():
        other_org = Organization(name="Other Org", slug="other-org")
        session.add(other_org)
        session.flush()
        other_facility = Facility(
            organization_id=other_org.id,
            name="Other Facility",
            code="OTHER-1",
            cultivation_enabled=True,
        )
        session.add(other_facility)
        session.flush()
        other_org_id, other_facility_id = other_org.id, other_facility.id

    other = service.current(other_org_id, other_facility_id)
    assert other.effective_mode == "doobielogic_sandbox"
    assert other.explicit is False
