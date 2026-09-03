from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationConfiguration
from modules.regulatory.models import RegulatoryFacilityMapping
from services.metrc_facility_onboarding import MetrcFacilityOnboardingService


KEY = "test-encryption-key"


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _setup(engine, *, existing_name: str = "", existing_license: str = ""):
    with Session(engine) as session, session.begin():
        org = Organization(name="Cowboy Kush", slug="cowboy-kush", active=True)
        session.add(org)
        session.flush()
        existing = None
        if existing_name:
            existing = Facility(
                organization_id=org.id,
                name=existing_name,
                code="EXISTING",
                license_number=existing_license,
                license_type="",
                active=True,
            )
            session.add(existing)
            session.flush()
        org_id = org.id
        existing_id = existing.id if existing else ""
    configs = IntegrationConfigurationService(engine, KEY)
    user = configs.save(
        scope_type="user",
        scope_key="admin|bootstrap",
        provider="metrc",
        organization_id=org_id,
        facility_id=existing_id or None,
        configuration={"state": "MA", "license_number": "", "environment": "sandbox"},
        secret="sandbox-user-key",
        actor="admin",
        audit_organization_id=org_id,
    )
    vendor = configs.save(
        scope_type="facility",
        scope_key=f"{org_id}:{existing_id or 'bootstrap'}:sandbox",
        provider="metrc_sandbox",
        organization_id=org_id,
        facility_id=existing_id or None,
        configuration={"state": "MA", "environment": "sandbox"},
        secret="vendor-key",
        actor="admin",
        audit_organization_id=org_id,
    )
    return org_id, existing_id, user, vendor


def _record(name="Cowboy Kush Manufacturing", license_number="MP281234"):
    return {
        "source": {
            "Id": 81722,
            "Name": name,
            "License": {"Number": license_number},
            "FacilityType": {"Name": "Marijuana Product Manufacturer"},
        }
    }


def test_no_candidate_creates_local_mirror_and_permanent_mapping_automatically():
    engine = _engine()
    org_id, _, user, vendor = _setup(engine)
    result = MetrcFacilityOnboardingService(engine, KEY).discover(
        organization_id=org_id,
        actor="admin",
        state="MA",
        environment="sandbox",
        records=[_record()],
        source_user_credential=user,
        source_vendor_credential=vendor,
    )

    row = result["facilities"][0]
    assert row["status"] == "created"
    assert row["mapping_permanent"] is True
    assert row["doobielogic_facility"]["name"] == "Cowboy Kush Manufacturing"
    assert row["doobielogic_facility"]["license_number"] == "MP281234"
    with Session(engine) as session:
        facility = session.scalar(select(Facility).where(Facility.organization_id == org_id, Facility.license_number == "MP281234"))
        mapping = session.scalar(select(RegulatoryFacilityMapping).where(RegulatoryFacilityMapping.facility_id == facility.id))
        cloned = session.scalar(select(IntegrationConfiguration).where(IntegrationConfiguration.facility_id == facility.id, IntegrationConfiguration.provider == "metrc"))
        assert facility.production_enabled is True
        assert mapping.provider_facility_id == "81722"
        assert mapping.environment == "sandbox"
        assert cloned is not None


def test_exact_license_reuses_existing_facility_without_duplicate():
    engine = _engine()
    org_id, existing_id, user, vendor = _setup(engine, existing_name="New Bedford Facility", existing_license="MP281234")
    result = MetrcFacilityOnboardingService(engine, KEY).discover(
        organization_id=org_id,
        actor="admin",
        state="MA",
        environment="sandbox",
        records=[_record()],
        source_user_credential=user,
        source_vendor_credential=vendor,
    )

    row = result["facilities"][0]
    assert row["status"] == "linked"
    assert row["match_reason"] == "exact_license"
    assert row["doobielogic_facility"]["id"] == existing_id
    with Session(engine) as session:
        assert len(list(session.scalars(select(Facility).where(Facility.organization_id == org_id)))) == 1


def test_name_only_match_requires_one_confirmation_instead_of_creating_duplicate():
    engine = _engine()
    org_id, existing_id, user, vendor = _setup(engine, existing_name="Cowboy Kush Manufacturing", existing_license="")
    service = MetrcFacilityOnboardingService(engine, KEY)
    result = service.discover(
        organization_id=org_id,
        actor="admin",
        state="MA",
        environment="sandbox",
        records=[_record()],
        source_user_credential=user,
        source_vendor_credential=vendor,
    )

    row = result["facilities"][0]
    assert row["status"] == "needs_confirmation"
    assert row["suggested_matches"][0]["id"] == existing_id
    assert result["needs_confirmation"] == 1
    with Session(engine) as session:
        assert len(list(session.scalars(select(Facility).where(Facility.organization_id == org_id)))) == 1

    confirmed = service.confirm(
        organization_id=org_id,
        actor="admin",
        state="MA",
        environment="sandbox",
        record=_record(),
        source_user_credential=user,
        source_vendor_credential=vendor,
        target_facility_id=existing_id,
    )
    assert confirmed["status"] == "linked"
    assert confirmed["match_reason"] == "administrator_confirmed"
