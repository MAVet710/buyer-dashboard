from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.metrc_facility_setup_snapshot import (
    augment_facility_setup_overview,
    read_facility_setup_snapshot,
)
from modules.coman.models import Base, Facility, Organization
from modules.regulatory.service import RegulatoryMappingService
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = {
    "locations": [{"provider_id": "loc-1", "name": "Flower 1", "source": {"Id": 1, "Name": "Flower 1"}}],
    "sublocations": [{"provider_id": "sub-1", "name": "Rack A", "source": {"Id": 2, "Name": "Rack A"}}],
    "location_types": [
        {"provider_id": "type-1", "name": "Default", "source": {"Id": 3, "Name": "Default"}},
        {"provider_id": "type-2", "name": "Quarantine", "source": {"Id": 4, "Name": "Quarantine"}},
    ],
    "strains": [
        {"provider_id": "strain-1", "name": "GMO", "source": {"Id": 5, "Name": "GMO"}},
        {"provider_id": "strain-2", "name": "Papaya", "source": {"Id": 6, "Name": "Papaya"}},
    ],
    "items": [
        {"provider_id": "item-1", "name": "GMO Flower", "source": {"Id": 7, "Name": "GMO Flower"}},
        {"provider_id": "item-2", "name": "Papaya Flower", "source": {"Id": 8, "Name": "Papaya Flower"}},
        {"provider_id": "item-3", "name": "GMO Pre-Roll", "source": {"Id": 9, "Name": "GMO Pre-Roll"}},
    ],
    "item_categories": [{"provider_id": "cat-1", "name": "Flower", "source": {"Id": 10, "Name": "Flower"}}],
    "item_brands": [{"provider_id": "brand-1", "name": "House", "source": {"Id": 11, "Name": "House"}}],
    "units_of_measure": [
        {"provider_id": "uom-1", "name": "Grams", "source": {"Id": 12, "Name": "Grams"}},
        {"provider_id": "uom-2", "name": "Each", "source": {"Id": 13, "Name": "Each"}},
    ],
}


def _facility():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Facility Snapshot", slug="facility-snapshot", active=True)
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


def _complete_resource(service, organization_id: str, facility_id: str, resource: str, records: list[dict]):
    service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource=resource,
        environment="sandbox",
        actor="admin",
        result={"ok": True, "http_status": 200, "records": records, "page_count": 1, "truncated": False},
        transport="test",
    )


def test_facility_setup_snapshot_exposes_current_master_data_without_metrc_request():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MP281234",
        provider_facility_id="metrc-facility-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    for resource, records in RESOURCES.items():
        _complete_resource(service, organization_id, facility_id, resource, records)

    context = RequestContext("user-1", organization_id, facility_id, "admin")
    snapshot = read_facility_setup_snapshot(context=context, engine=engine)

    assert snapshot["ready"] is True
    assert snapshot["network_request_made"] is False
    assert snapshot["source"] == "integration_provider_snapshots"
    assert snapshot["summary"] == {
        "active_location_count": 1,
        "active_sublocation_count": 1,
        "location_type_count": 2,
        "active_strain_count": 2,
        "active_item_count": 3,
        "item_category_count": 1,
        "item_brand_count": 1,
        "unit_of_measure_count": 2,
    }
    assert snapshot["resources"]["locations"]["records"][0]["source"]["Name"] == "Flower 1"


def test_existing_facility_setup_overview_is_augmented_with_visible_synced_counts():
    engine, organization_id, facility_id = _facility()
    RegulatoryMappingService(engine).verify(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction_code="MA",
        license_number="MP281234",
        provider_facility_id="metrc-facility-1",
        environment="sandbox",
        integration_configuration_id=None,
        actor="admin",
    )
    service = SnapshottingMetrcFacilityBootstrapService(engine)
    for resource, records in RESOURCES.items():
        _complete_resource(service, organization_id, facility_id, resource, records)

    overview = {
        "metrc": {"message": "Connected."},
        "sections": [
            {"key": "rooms", "label": "Rooms & Locations", "priority": "P0", "status": "live-read", "description": "old"},
            {"key": "strains", "label": "Strains", "priority": "P0", "status": "live-read", "description": "old"},
            {"key": "items", "label": "Products & Metrc Items", "priority": "P0", "status": "live-read", "description": "old"},
            {"key": "production", "label": "Production Processes", "priority": "P1", "status": "live-read", "description": "unchanged"},
        ],
    }
    context = RequestContext("user-1", organization_id, facility_id, "admin")
    result = augment_facility_setup_overview(overview, context=context, engine=engine)
    sections = {row["key"]: row for row in result["sections"]}

    assert sections["rooms"]["label"] == "Rooms & Locations · 1 / 1"
    assert sections["strains"]["label"] == "Strains · 2"
    assert sections["items"]["label"] == "Products & Metrc Items · 3"
    assert sections["rooms"]["status"] == "synced"
    assert "3 active items" in sections["items"]["description"]
    assert sections["production"]["description"] == "unchanged"
    assert result["metrc"]["synchronized_state"]["network_request_made"] is False
    assert "loaded locally" in result["metrc"]["message"]


def test_location_settings_frontend_renders_backend_section_labels_on_normal_page_load():
    source = (ROOT / "frontend/src/pages/LocationSettingsPage.tsx").read_text(encoding="utf-8")
    assert 'apiGet<FacilitySetup>("/api/v1/location-settings/facility-setup"' in source
    assert "setup.data.sections.map(section" in source
    assert "{section.label}" in source
