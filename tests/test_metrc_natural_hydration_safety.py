from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, Organization, utc_now
from modules.cultivation.models import CultivationPlant
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
        session.add(Organization(id="org-safe", name="Hydration Safety", slug="hydration-safety"))
        session.add(Facility(
            id="fac-safe",
            organization_id="org-safe",
            name="Hydration Safety Facility",
            code="MC281234",
            license_number="MC281234",
            cultivation_enabled=True,
            production_enabled=True,
        ))
    return engine


def _normalized(resource: str, rows: list[dict]):
    return [
        {
            "provider": "metrc",
            "jurisdiction_code": "MA",
            "resource": resource,
            "provider_id": str(row.get("Id") or ""),
            "label": str(row.get("Label") or ""),
            "name": str(row.get("Name") or row.get("StrainName") or ""),
            "source": dict(row),
        }
        for row in rows
    ]


def _baseline(engine, resource: str, cursor: str = "initial-full"):
    now = utc_now()
    with Session(engine) as session, session.begin():
        session.add(IntegrationSyncState(
            organization_id="org-safe",
            facility_id="fac-safe",
            provider="metrc",
            resource=resource,
            environment="sandbox",
            cursor=cursor,
            status="succeeded",
            last_started_at=now,
            last_completed_at=now,
            last_success_at=now,
            records_seen=0,
            records_written=0,
            updated_by="tester",
        ))


def test_full_hydration_projects_verified_cultivation_when_one_dependency_fails(monkeypatch):
    engine = _engine()
    location = {"Id": "loc-1", "Name": "VEG 1"}
    plant = {
        "Id": "plant-1",
        "Label": "1A4FF0100000000000000201",
        "StrainName": "GMO",
        "LocationId": "loc-1",
        "LocationName": "VEG 1",
    }

    def fake_normalized(self, *, resource, **_kwargs):
        if resource == "plants_flowering":
            return {"ok": False, "http_status": 500, "status": "failed", "message": "temporary provider error"}
        rows = {
            "locations_active": [location],
            "plants_vegetative": [plant],
            "plant_batches_active": [],
            "harvests_active": [],
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
        organization_id="org-safe",
        facility_id="fac-safe",
        license_number="MC281234",
        state="MA",
        environment="sandbox",
        integrator_api_key="integrator",
        user_api_key="user",
        actor="tester",
    )

    hydration = result["workspace_hydration"]
    gate = hydration["workspace_gates"]["cultivation"]
    assert gate["status"] == "partial_current"
    assert "plants_flowering" in gate["missing_or_restricted_resources"]
    assert gate["independently_verified_resources_project"] is True
    assert gate["unrelated_resource_failure_blocks_projection"] is False
    assert "cultivation" in hydration["workspaces"]
    with Session(engine) as session:
        plants = list(session.scalars(select(CultivationPlant)))
        assert len(plants) == 1
        assert plants[0].plant_tag == "1A4FF0100000000000000201"


def test_incremental_permission_skipped_resource_is_not_reclassified_as_missing(monkeypatch):
    engine = _engine()
    _baseline(engine, "sales_deliveries", cursor="permission-skipped")

    def forbidden_fetch(**_kwargs):
        raise AssertionError("permission-skipped resource must not be read incrementally")

    monkeypatch.setattr(bootstrap_module, "fetch_metrc_resource", forbidden_fetch)
    result = MetrcIncrementalSyncService(engine).sync(
        organization_id="org-safe",
        facility_id="fac-safe",
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        integrator_api_key="integrator",
        user_api_key="user",
        actor="tester",
    )

    row = next(item for item in result["resources"] if item["resource"] == "sales_deliveries")
    assert row["status"] == "skipped"
    assert result["totals"]["skipped"] == 1


def test_incremental_cultivation_delta_waits_for_complete_cultivation_baseline(monkeypatch):
    engine = _engine()
    _baseline(engine, "locations")
    _baseline(engine, "plants_vegetative")
    location = {"Id": "loc-1", "Name": "VEG 1"}
    plant = {
        "Id": "plant-1",
        "Label": "1A4FF0100000000000000202",
        "StrainName": "GMO",
        "LocationId": "loc-1",
        "LocationName": "VEG 1",
    }

    def fake_fetch(**kwargs):
        resource = kwargs["resource"]
        rows = {"locations_active": [location], "plants_vegetative": [plant]}[resource]
        return {
            "ok": True,
            "http_status": 200,
            "payload": {"Data": rows, "TotalPages": 1},
            "records": _normalized(resource, rows),
        }

    monkeypatch.setattr(bootstrap_module, "fetch_metrc_resource", fake_fetch)
    monkeypatch.setattr(incremental_module, "MetrcWorkspaceHydrationService", MetrcWorkspaceHydrationService)

    result = MetrcIncrementalSyncService(engine).sync(
        organization_id="org-safe",
        facility_id="fac-safe",
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        integrator_api_key="integrator",
        user_api_key="user",
        actor="tester",
    )

    gate = result["workspace_hydration"]["workspace_gates"]["cultivation"]
    assert gate["status"] == "withheld_incomplete_baseline"
    with Session(engine) as session:
        assert list(session.scalars(select(CultivationPlant))) == []
