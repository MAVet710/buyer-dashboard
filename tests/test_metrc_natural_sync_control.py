from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.metrc_context import MetrcContext
from backend.app.services.metrc_natural_sync import MetrcNaturalSyncControlService, _expected_resources
from modules.coman.models import Base, Facility, Organization, utc_now
from modules.integrations.models import IntegrationSyncState


def _engine():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-natural-control",name="Natural Control",slug="natural-control"))
        session.add(Facility(id="fac-natural-control",organization_id="org-natural-control",name="Natural Control",code="NCTL"))
    return engine


def _metrc():
    return MetrcContext(
        configured=True,state="MA",license_number="MP281234",user_api_key="user",integrator_api_key="integrator",
        status="connected",environment="sandbox",trusted_mapping=True,message="ready",row=object(),mapping=object(),
    )


def _mark_full_baseline(engine):
    now=utc_now()
    with Session(engine) as session, session.begin():
        for index,resource in enumerate(_expected_resources()):
            session.add(IntegrationSyncState(
                organization_id="org-natural-control",facility_id="fac-natural-control",provider="metrc",resource=resource,
                environment="sandbox",cursor="permission-skipped" if index%7==0 else "initial-full",status="succeeded",
                last_started_at=now,last_completed_at=now,last_success_at=now,last_error="",records_seen=1,records_written=1,updated_by="test",
            ))


def test_sync_uses_authenticated_full_hydration_until_every_bootstrap_resource_has_a_resolved_baseline(monkeypatch):
    engine=_engine()
    calls=[]
    def full_sync(self,**kwargs):
        calls.append(("full",kwargs["license_number"]))
        return {"totals":{"failed":0,"records":3},"resources":[{"resource":"packages","status":"succeeded","record_count":3,"accepted_count":3,"duplicate_count":0,"transport":"metrc"}]}
    def incremental(self,**kwargs):
        calls.append(("incremental",kwargs["license_number"]))
        raise AssertionError("incremental sync must not run before a complete baseline")
    monkeypatch.setattr("backend.app.services.metrc_natural_sync.ResilientSnapshottingMetrcFacilityBootstrapService.sync",full_sync)
    monkeypatch.setattr("backend.app.services.metrc_natural_sync.MetrcIncrementalSyncService.sync",incremental)

    result=MetrcNaturalSyncControlService(engine).sync(
        organization_id="org-natural-control",facility_id="fac-natural-control",metrc=_metrc(),actor="admin"
    )
    assert calls==[("full","MP281234")]
    assert result["sync_mode"]=="full_hydration"
    assert result["authenticated_provider_data"] is True
    assert result["transport"]=="metrc_authenticated_full"


def test_same_sync_control_switches_to_incremental_only_after_full_baseline(monkeypatch):
    engine=_engine();_mark_full_baseline(engine)
    service=MetrcNaturalSyncControlService(engine)
    assert service.full_baseline_ready(organization_id="org-natural-control",facility_id="fac-natural-control",environment="sandbox") is True
    calls=[]
    def full_sync(self,**kwargs):
        raise AssertionError("full hydration should not replay after a complete baseline")
    def incremental(self,**kwargs):
        calls.append(("incremental",kwargs["license_number"]))
        return {
            "totals":{"failed":0,"records":2},
            "resources":[{"resource":"packages","status":"succeeded","record_count":2,"last_modified_start":"2026-09-04T19:00:00+00:00","current_snapshot":{"duplicates":0}}],
            "workspace_hydration":{"automatic":True,"workspaces":{}},
        }
    monkeypatch.setattr("backend.app.services.metrc_natural_sync.ResilientSnapshottingMetrcFacilityBootstrapService.sync",full_sync)
    monkeypatch.setattr("backend.app.services.metrc_natural_sync.MetrcIncrementalSyncService.sync",incremental)

    result=service.sync(organization_id="org-natural-control",facility_id="fac-natural-control",metrc=_metrc(),actor="admin")
    assert calls==[("incremental","MP281234")]
    assert result["sync_mode"]=="incremental"
    assert result["transport"]=="metrc_last_modified_delta"
    assert result["totals"]["records"]==2


def test_runtime_status_reports_real_metrc_resource_state_not_fixture_contract():
    engine=_engine();_mark_full_baseline(engine)
    status=MetrcNaturalSyncControlService(engine).status(
        organization_id="org-natural-control",facility_id="fac-natural-control",metrc=_metrc()
    )
    assert status["provider"]=="metrc"
    assert status["provider_id"]=="metrc"
    assert status["read_mode"]=="authenticated_metrc_regulatory_snapshot"
    assert status["authenticated_provider_data"] is True
    assert status["full_baseline_ready"] is True
    assert set(status["resources"])==set(_expected_resources())
    assert "transfers" not in status["resources"]  # deterministic DEV fixture resource name is not the authenticated contract
    assert "incoming_transfers" in status["resources"]
    assert "packages" in status["resources"]
