from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.integrations.models import IntegrationSyncRecord, IntegrationSyncState
from services.metrc_facility_bootstrap import MetrcFacilityBootstrapService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Cowboy Kush", slug="cowboy-kush", active=True)
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Cowboy Kush Manufacturing",
            code="MP281234",
            license_number="MP281234",
            production_enabled=True,
            commercial_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, org.id, facility.id


def test_bootstrap_cascades_master_tags_and_operational_resources(monkeypatch):
    engine, org_id, facility_id = _engine()

    def fake_normalized(**kwargs):
        resource = kwargs["resource"]
        return {
            "ok": True,
            "http_status": 200,
            "records": [{"source": {"Id": f"{resource}-1", "Name": resource}}],
        }

    def fake_get(self, path, params=None, **_kwargs):
        return {
            "ok": True,
            "http_status": 200,
            "payload": [{"Id": f"{path}-1", "Name": path}],
        }

    monkeypatch.setattr("services.metrc_facility_bootstrap.fetch_metrc_resource", fake_normalized)
    monkeypatch.setattr("services.metrc_facility_bootstrap.MetrcTransport.get", fake_get)

    result = MetrcFacilityBootstrapService(engine).sync(
        organization_id=org_id,
        facility_id=facility_id,
        license_number="MP281234",
        state="MA",
        environment="sandbox",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        actor="admin",
        facility_record={"Id": 81722, "Name": "Cowboy Kush Manufacturing", "Permissions": ["Manage Packages"]},
    )

    assert result["totals"]["failed"] == 0
    assert result["totals"]["skipped"] == 0
    assert result["totals"]["resources"] == 16
    assert result["totals"]["records"] == 16
    names = {row["resource"] for row in result["resources"]}
    assert {
        "facility_profile", "locations", "sublocations", "location_types", "strains", "items",
        "item_categories", "item_brands", "units_of_measure", "package_tags", "plant_tags",
        "packages", "plant_batches", "plants_vegetative", "plants_flowering", "harvests",
    } == names
    with Session(engine) as session:
        stored = list(session.scalars(select(IntegrationSyncRecord).where(
            IntegrationSyncRecord.organization_id == org_id,
            IntegrationSyncRecord.facility_id == facility_id,
            IntegrationSyncRecord.provider == "metrc",
        )))
        assert len(stored) == 16
        facility_profile = next(row for row in stored if row.resource == "facility_profile")
        assert "Manage Packages" in facility_profile.raw_payload_json


def test_permission_specific_resource_is_skipped_without_breaking_onboarding(monkeypatch):
    engine, org_id, facility_id = _engine()

    def fake_normalized(**kwargs):
        if kwargs["resource"] == "plant_tags_available":
            return {"ok": False, "http_status": 403, "status": "forbidden", "message": "No plant-tag permission"}
        return {"ok": True, "http_status": 200, "records": []}

    def fake_get(self, path, params=None, **_kwargs):
        return {"ok": True, "http_status": 200, "payload": []}

    monkeypatch.setattr("services.metrc_facility_bootstrap.fetch_metrc_resource", fake_normalized)
    monkeypatch.setattr("services.metrc_facility_bootstrap.MetrcTransport.get", fake_get)

    result = MetrcFacilityBootstrapService(engine).sync(
        organization_id=org_id,
        facility_id=facility_id,
        license_number="MP281234",
        state="MA",
        environment="sandbox",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        actor="admin",
    )

    plant_tags = next(row for row in result["resources"] if row["resource"] == "plant_tags")
    assert plant_tags["status"] == "skipped"
    assert result["totals"]["skipped"] == 1
    assert result["totals"]["failed"] == 0
    with Session(engine) as session:
        state = session.scalar(select(IntegrationSyncState).where(
            IntegrationSyncState.facility_id == facility_id,
            IntegrationSyncState.provider == "metrc",
            IntegrationSyncState.resource == "plant_tags",
        ))
        assert state.status == "succeeded"
        assert state.cursor == "permission-skipped"
