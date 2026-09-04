from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.integrations import IntegrationConfigurationService
from modules.regulatory.models import RegulatoryFacilityMapping
from services.metrc_facility_onboarding import MetrcFacilityOnboardingService


KEY = "multi-license-test-key"


def _provider_record(*, provider_id: int, name: str, license_number: str, license_type: str) -> dict:
    return {
        "source": {
            "Id": provider_id,
            "Name": name,
            "License": {"Number": license_number},
            "FacilityType": {"Name": license_type},
        }
    }


def test_one_metrc_user_discovers_and_scopes_every_accessible_sandbox_license_exactly():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session, session.begin():
        organization = Organization(name="Multi License Operator", slug="multi-license-operator", active=True)
        session.add(organization)
        session.flush()
        organization_id = organization.id

    configs = IntegrationConfigurationService(engine, KEY)
    source_user = configs.save(
        scope_type="user",
        scope_key="admin|bootstrap",
        provider="metrc",
        organization_id=organization_id,
        facility_id=None,
        configuration={"state": "MA", "license_number": "", "environment": "sandbox"},
        secret="shared-metrc-user-key",
        actor="admin",
        audit_organization_id=organization_id,
    )
    source_vendor = configs.save(
        scope_type="facility",
        scope_key=f"{organization_id}:bootstrap:sandbox",
        provider="metrc_sandbox",
        organization_id=organization_id,
        facility_id=None,
        configuration={"state": "MA", "environment": "sandbox"},
        secret="shared-metrc-vendor-key",
        actor="admin",
        audit_organization_id=organization_id,
    )

    records = [
        _provider_record(
            provider_id=1001,
            name="Sandbox Cultivation",
            license_number="MC281001",
            license_type="Marijuana Cultivator",
        ),
        _provider_record(
            provider_id=1002,
            name="Sandbox Manufacturing",
            license_number="MP281002",
            license_type="Marijuana Product Manufacturer",
        ),
        _provider_record(
            provider_id=1003,
            name="Sandbox Retail",
            license_number="MR281003",
            license_type="Marijuana Retailer",
        ),
    ]

    service = MetrcFacilityOnboardingService(engine, KEY)
    first = service.discover(
        organization_id=organization_id,
        actor="admin",
        state="MA",
        environment="sandbox",
        records=records,
        source_user_credential=source_user,
        source_vendor_credential=source_vendor,
        auto_create=True,
    )

    assert first["auto_created"] == 3
    assert first["auto_linked"] == 0
    assert first["needs_confirmation"] == 0
    assert {row["license_number"] for row in first["facilities"]} == {"MC281001", "MP281002", "MR281003"}

    with Session(engine) as session:
        facilities = list(session.scalars(select(Facility).where(Facility.organization_id == organization_id)))
        mappings = list(session.scalars(select(RegulatoryFacilityMapping).where(
            RegulatoryFacilityMapping.organization_id == organization_id,
            RegulatoryFacilityMapping.provider == "metrc",
            RegulatoryFacilityMapping.environment == "sandbox",
        )))

    assert len(facilities) == 3
    assert len(mappings) == 3
    facility_by_license = {facility.license_number: facility for facility in facilities}
    mapping_by_license = {mapping.license_number: mapping for mapping in mappings}
    assert set(facility_by_license) == {"MC281001", "MP281002", "MR281003"}
    assert set(mapping_by_license) == set(facility_by_license)

    expected_provider_ids = {"MC281001": "1001", "MP281002": "1002", "MR281003": "1003"}
    for license_number, facility in facility_by_license.items():
        mapping = mapping_by_license[license_number]
        assert mapping.facility_id == facility.id
        assert mapping.jurisdiction_code == "MA"
        assert mapping.provider_facility_id == expected_provider_ids[license_number]

        user = configs.get("user", f"admin|{facility.id}", "metrc")
        vendor = configs.get("facility", f"{organization_id}:{facility.id}:sandbox", "metrc_sandbox")
        assert user is not None
        assert vendor is not None
        assert user.organization_id == organization_id
        assert user.facility_id == facility.id
        assert vendor.organization_id == organization_id
        assert vendor.facility_id == facility.id

        user_config = configs.public(user)["configuration"]
        vendor_config = configs.public(vendor)["configuration"]
        assert user_config == {"state": "MA", "license_number": license_number, "environment": "sandbox"}
        assert vendor_config["state"] == "MA"
        assert vendor_config["license_number"] == license_number
        assert vendor_config["environment"] == "sandbox"
        assert configs.secret(user) == "shared-metrc-user-key"
        assert configs.secret(vendor) == "shared-metrc-vendor-key"

    # Discovery is replay-safe: the same three Metrc licenses re-link to the exact
    # same local facilities instead of creating duplicate workspaces or mappings.
    second = service.discover(
        organization_id=organization_id,
        actor="admin",
        state="MA",
        environment="sandbox",
        records=records,
        source_user_credential=source_user,
        source_vendor_credential=source_vendor,
        auto_create=True,
    )
    assert second["auto_created"] == 0
    assert second["auto_linked"] == 3
    assert all(row["status"] == "linked" for row in second["facilities"])

    with Session(engine) as session:
        assert len(list(session.scalars(select(Facility).where(Facility.organization_id == organization_id)))) == 3
        assert len(list(session.scalars(select(RegulatoryFacilityMapping).where(
            RegulatoryFacilityMapping.organization_id == organization_id,
            RegulatoryFacilityMapping.provider == "metrc",
            RegulatoryFacilityMapping.environment == "sandbox",
        )))) == 3
