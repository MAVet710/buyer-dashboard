from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization, utc_now
from modules.cultivation.models import CultivationPlant, CultivationPlantEvent
from modules.integrations.models import IntegrationSyncState
from services import metrc_facility_bootstrap as bootstrap_module
from services import metrc_incremental_sync as incremental_module
from services.metrc_expanded_workspace_hydration import MetrcWorkspaceHydrationService
from services.metrc_incremental_sync import MetrcIncrementalSyncService
from services.metrc_natural_bootstrap import NaturalMetrcFacilityBootstrapService


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-cult-sync", name="Cultivation Sync", slug="cultivation-sync"))
        session.add(Facility(
            id="fac-cult-sync",
            organization_id="org-cult-sync",
            name="Cultivation Sync Facility",
            code="MC281234",
            license_number="MC281234",
            cultivation_enabled=True,
            production_enabled=True,
        ))
    return engine


def _normalized(resource: str, rows: list[dict]):
    output = []
    for row in rows:
        output.append({
            "provider": "metrc",
            "jurisdiction_code": "MA",
            "resource": resource,
            "provider_id": str(row.get("Id") or ""),
            "label": str(row.get("Label") or ""),
            "name": str(row.get("Name") or row.get("StrainName") or ""),
            "status": str(row.get("Status") or ""),
            "last_modified": str(row.get("LastModified") or ""),
            "source": dict(row),
        })
    return output


def _provider_rows():
    location = {"Id": "loc-1", "Name": "VEG 1"}
    batch = {"Id": "batch-1", "Name": "GMO CLONES", "StrainName": "GMO", "Type": "Clone", "LocationId": "loc-1", "LocationName": "VEG 1"}
    plant = {"Id": "plant-1", "Label": "1A4FF0100000000000000101", "StrainName": "GMO", "LocationId": "loc-1", "LocationName": "VEG 1", "PlantBatchId": "batch-1"}
    harvest = {"Id": "harvest-1", "Name": "GMO H1", "SourceStrainNames": ["GMO"], "DryingLocationId": "loc-1", "DryingLocationName": "VEG 1", "CurrentPlantCount": 1}
    return location, batch, plant, harvest


def test_full_authenticated_hydration_populates_cultivation_workspace(monkeypatch):
    engine = _engine()
    location, batch, plant, harvest = _provider_rows()

    def fake_normalized(self, *, resource, **_kwargs):
        rows = {
            "locations_active": [location],
            "plant_batches_active": [batch],
            "plants_vegetative": [plant],
            "plants_flowering": [],
            "harvests_active": [harvest],
        }.get(resource, [])
        return {
            "ok": True,
            "http_status": 200,
            "payload": {"Data": rows, "TotalPages": 1},
            "records": _normalized(resource, rows),
            "page_count": 1,
            "truncated": False,
        }

    def fake_direct(self, **_kwargs):
        return {"ok": True, "http_status": 200, "payload": {"Data": [], "TotalPages": 1}, "records": [], "page_count": 1, "truncated": False}

    monkeypatch.setattr(NaturalMetrcFacilityBootstrapService, "_fetch_all_normalized", fake_normalized)
    monkeypatch.setattr(NaturalMetrcFacilityBootstrapService, "_fetch_all_direct", fake_direct)

    result = NaturalMetrcFacilityBootstrapService(engine).sync(
        organization_id="org-cult-sync",
        facility_id="fac-cult-sync",
        license_number="MC281234",
        state="MA",
        environment="sandbox",
        integrator_api_key="integrator",
        user_api_key="user",
        actor="tester",
    )

    cultivation = result["workspace_hydration"]["workspaces"]["cultivation"]
    assert cultivation["created_rooms"] == 1
    assert cultivation["created_groups"] == 1
    assert cultivation["created_plants"] == 1
    assert cultivation["created_harvests"] == 1
    assert result["workspace_hydration"]["complete_snapshot_only"] is True
    with Session(engine) as session:
        plants = list(session.scalars(select(CultivationPlant)))
        assert len(plants) == 1
        assert plants[0].plant_tag == "1A4FF0100000000000000101"
        assert list(session.scalars(select(CultivationPlantEvent))) == []


def test_incremental_changed_cultivation_records_materialize_without_deleting_omissions(monkeypatch):
    engine = _engine()
    location, batch, plant, harvest = _provider_rows()
    baseline_time = utc_now()
    resource_map = {
        "locations": "locations_active",
        "plant_batches": "plant_batches_active",
        "plants_vegetative": "plants_vegetative",
        "plants_flowering": "plants_flowering",
        "harvests": "harvests_active",
    }
    with Session(engine) as session, session.begin():
        for local in resource_map:
            session.add(IntegrationSyncState(
                organization_id="org-cult-sync",
                facility_id="fac-cult-sync",
                provider="metrc",
                resource=local,
                environment="sandbox",
                cursor="initial-full",
                status="succeeded",
                last_started_at=baseline_time,
                last_completed_at=baseline_time,
                last_success_at=baseline_time,
                records_seen=0,
                records_written=0,
                updated_by="tester",
            ))

    rows_by_provider_resource = {
        "locations_active": [location],
        "plant_batches_active": [batch],
        "plants_vegetative": [plant],
        "plants_flowering": [],
        "harvests_active": [harvest],
    }

    def fake_fetch(**kwargs):
        resource = kwargs["resource"]
        rows = rows_by_provider_resource[resource]
        return {
            "ok": True,
            "http_status": 200,
            "payload": {"Data": rows, "TotalPages": 1},
            "records": _normalized(resource, rows),
        }

    monkeypatch.setattr(bootstrap_module, "fetch_metrc_resource", fake_fetch)
    monkeypatch.setattr(incremental_module, "MetrcWorkspaceHydrationService", MetrcWorkspaceHydrationService)

    result = MetrcIncrementalSyncService(engine).sync(
        organization_id="org-cult-sync",
        facility_id="fac-cult-sync",
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        integrator_api_key="integrator",
        user_api_key="user",
        actor="tester",
    )

    cultivation = result["workspace_hydration"]["workspaces"]["cultivation"]
    assert cultivation["created_plants"] == 1
    assert result["destructive_membership_replacement"] is False
    assert result["periodic_full_snapshot_required_for_absence"] is True
    assert all(
        row.get("omitted_rows_marked_absent") is False
        for row in result["resources"]
        if row["status"] == "succeeded"
    )
