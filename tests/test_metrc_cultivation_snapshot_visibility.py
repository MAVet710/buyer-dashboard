from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.metrc_cultivation_snapshot import cultivation_regulatory_snapshot_from_sync
from modules.coman.models import Base, Facility, Organization
from modules.cultivation.models import CultivationPlant
from modules.regulatory.service import RegulatoryMappingService
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


ROOT = Path(__file__).resolve().parents[1]


def _facility():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Cultivation Snapshot", slug="cultivation-snapshot", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Cultivation Facility",
            code="CUL-SNAPSHOT",
            license_number="MC281234",
            cultivation_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        session.add(
            CultivationPlant(
                organization_id=organization.id,
                facility_id=facility.id,
                plant_tag="1A4FF0100000000000000001",
                strain_name="GMO",
                phase="vegetative",
                room_code="VEG 1",
            )
        )
        return engine, organization.id, facility.id


def _sync_resource(service, *, organization_id: str, facility_id: str, resource: str, records: list[dict]):
    return service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource=resource,
        environment="sandbox",
        actor="admin",
        result={
            "ok": True,
            "http_status": 200,
            "records": records,
            "page_count": 1,
            "truncated": False,
        },
        transport="test",
    )


def test_cultivation_uses_local_current_metrc_snapshot_without_provider_request():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MC281234",
        provider_facility_id="metrc-facility-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    _sync_resource(
        service,
        organization_id=organization_id,
        facility_id=facility_id,
        resource="plant_batches",
        records=[{"provider_id": "batch-1", "name": "GMO clones", "source": {"Id": 1, "Name": "GMO clones"}}],
    )
    _sync_resource(
        service,
        organization_id=organization_id,
        facility_id=facility_id,
        resource="plants_vegetative",
        records=[{
            "provider_id": "plant-1",
            "label": "1A4FF0100000000000000001",
            "name": "GMO",
            "source": {"Id": 2, "Label": "1A4FF0100000000000000001", "StrainName": "GMO", "LocationName": "VEG 1"},
        }],
    )
    _sync_resource(
        service,
        organization_id=organization_id,
        facility_id=facility_id,
        resource="plants_flowering",
        records=[],
    )
    _sync_resource(
        service,
        organization_id=organization_id,
        facility_id=facility_id,
        resource="harvests",
        records=[{"provider_id": "harvest-1", "name": "GMO H1", "source": {"Id": 3, "Name": "GMO H1"}}],
    )

    result = cultivation_regulatory_snapshot_from_sync(
        context=RequestContext("user-1", organization_id, facility_id, "admin"),
        engine=engine,
    )

    assert result["ready"] is True
    assert result["source"] == "integration_provider_snapshots"
    assert result["network_request_made"] is False
    assert result["summary"] == {
        "active_plant_batch_count": 1,
        "vegetative_plant_count": 1,
        "flowering_plant_count": 0,
        "active_harvest_count": 1,
    }
    assert result["reconciliation"]["summary"]["status"] == "clean"
    assert result["reconciliation"]["summary"]["matched_plant_count"] == 1
    assert result["live_verification_endpoint"].endswith("/plants/regulatory")


def test_cultivation_withholds_reconciliation_until_both_plant_phase_snapshots_complete():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MC281234",
        provider_facility_id="metrc-facility-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    _sync_resource(service, organization_id=organization_id, facility_id=facility_id, resource="plant_batches", records=[])
    _sync_resource(service, organization_id=organization_id, facility_id=facility_id, resource="plants_vegetative", records=[])
    _sync_resource(service, organization_id=organization_id, facility_id=facility_id, resource="harvests", records=[])

    result = cultivation_regulatory_snapshot_from_sync(
        context=RequestContext("user-1", organization_id, facility_id, "admin"),
        engine=engine,
    )

    assert result["ready"] is False
    assert result["resources"]["flowering_plants"]["status"] == "not_synced"
    assert result["reconciliation"] is None


def test_cultivation_frontend_loads_synced_state_and_keeps_live_check_explicit():
    source = (ROOT / "frontend/src/components/CultivationRegulatoryHealth.tsx").read_text(encoding="utf-8")
    assert "/api/v1/inventory/production/plants/regulatory-snapshot" in source
    assert "/api/v1/inventory/production/plants/regulatory" in source
    assert "Verify live" in source
    assert "no Metrc request on page load" in source
