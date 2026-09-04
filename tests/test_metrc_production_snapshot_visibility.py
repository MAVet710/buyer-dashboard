from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.metrc_production_snapshot import manufacturing_regulatory_snapshot_from_sync
from modules.coman.models import Base, Facility, Organization
from modules.regulatory.service import RegulatoryMappingService
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


ROOT = Path(__file__).resolve().parents[1]


def _facility():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Production Snapshot", slug="production-snapshot", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Manufacturing Facility",
            code="MP281234",
            license_number="MP281234",
            production_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, organization.id, facility.id


def _complete(service, organization_id: str, facility_id: str, resource: str, records: list[dict]):
    service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource=resource,
        environment="sandbox",
        actor="admin",
        result={"ok": True, "http_status": 200, "records": records, "page_count": 1, "truncated": False},
        transport="test",
    )


def test_production_snapshot_surfaces_provider_processing_jobs_without_network_request():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MP281234",
        provider_facility_id="metrc-production-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    _complete(
        service,
        organization_id,
        facility_id,
        "packages",
        [
            {"provider_id": "pkg-1", "label": "1A4FF0100000000000000101", "source": {"Id": 101, "Label": "1A4FF0100000000000000101"}},
            {"provider_id": "pkg-2", "label": "1A4FF0100000000000000102", "source": {"Id": 102, "Label": "1A4FF0100000000000000102"}},
        ],
    )
    _complete(
        service,
        organization_id,
        facility_id,
        "processing_jobs",
        [{
            "provider_id": "proc-1",
            "name": "GMO Infusion",
            "status": "Active",
            "source": {
                "Id": 201,
                "Name": "GMO Infusion",
                "Status": "Active",
                "JobTypeName": "Infusion",
                "LocationName": "Kitchen",
                "PackageLabel": "1A4FF0100000000000000101",
            },
        }],
    )

    result = manufacturing_regulatory_snapshot_from_sync(
        context=RequestContext("user-1", organization_id, facility_id, "admin"),
        engine=engine,
    )

    assert result["configured"] is True
    assert result["ready"] is True
    assert result["network_request_made"] is False
    assert result["source"] == "integration_provider_snapshots"
    assert result["summary"] == {"active_package_count": 2, "active_processing_job_count": 1}
    assert result["resources"]["processing_jobs"]["records"][0] == {
        "provider_id": "proc-1",
        "name": "GMO Infusion",
        "status": "Active",
        "job_type": "Infusion",
        "location": "Kitchen",
        "package_label": "1A4FF0100000000000000101",
        "started_at": "",
        "last_modified": "",
    }
    assert result["live_verification_endpoint"].endswith("/production/regulatory/manufacturing")


def test_production_snapshot_does_not_fabricate_local_jobs_when_provider_processing_history_exists():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MP281234",
        provider_facility_id="metrc-production-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    _complete(service, organization_id, facility_id, "packages", [])
    _complete(
        service,
        organization_id,
        facility_id,
        "processing_jobs",
        [{"provider_id": "proc-1", "name": "External Job", "source": {"Id": 201, "Name": "External Job"}}],
    )

    from modules.coman.repository import ComanRepository

    before = ComanRepository(engine).list_production_orders(organization_id, facility_id)
    result = manufacturing_regulatory_snapshot_from_sync(
        context=RequestContext("user-1", organization_id, facility_id, "admin"),
        engine=engine,
    )
    after = ComanRepository(engine).list_production_orders(organization_id, facility_id)

    assert before == []
    assert after == []
    assert result["summary"]["active_processing_job_count"] == 1
    assert result["read_only"] is True


def test_production_frontend_loads_synced_state_and_keeps_live_verification_explicit():
    page = (ROOT / "frontend/src/pages/ProductionPage.tsx").read_text(encoding="utf-8")
    component = (ROOT / "frontend/src/components/ProductionRegulatoryState.tsx").read_text(encoding="utf-8")
    assert "<ProductionRegulatoryState />" in page
    assert "/api/v1/inventory/production/regulatory/manufacturing-snapshot" in component
    assert "/api/v1/inventory/production/regulatory/manufacturing" in component
    assert "enabled: false" in component
    assert "Verify live" in component
    assert "no Metrc request on page load" in component
