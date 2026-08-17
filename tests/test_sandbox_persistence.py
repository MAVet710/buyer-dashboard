from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.data_hub_repository import DataHubRepository
from services.demo_data import build_demo_payload
from services.sandbox_persistence import persist_sandbox_sources, restore_sandbox_sources


def _repository_with_scope():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(name="DEV Sandbox", slug="dev-sandbox", active=True)
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Sandbox Facility",
            code="SANDBOX",
            timezone_name="America/New_York",
            active=True,
        )
        session.add(facility)
        session.commit()
        return DataHubRepository(engine), org.id, facility.id


def test_sandbox_sources_round_trip_through_data_hub_repository():
    repository, organization_id, facility_id = _repository_with_scope()
    state = {
        "active_organization_id": organization_id,
        "active_facility_id": facility_id,
        "demo_company_seed": 710,
        "demo_catalog_seed": 811,
        "demo_history_seed": 912,
        "demo_selected_scenario": "Healthy baseline",
    }
    payload = build_demo_payload(today=date(2026, 8, 17), scale="small")

    count = persist_sandbox_sources(
        state,
        payload,
        version="test-version",
        actor="pytest",
        repository=repository,
    )
    restored = restore_sandbox_sources(state, repository=repository)

    assert count >= 20
    assert restored.available is True
    assert restored.manifest["version"] == "test-version"
    assert restored.manifest["as_of_date"] == "2026-08-17"
    assert restored.manifest["selected_scenario"] == "Healthy baseline"
    assert "buyer_inventory" in restored.sources
    assert "extraction_runs" in restored.sources
    assert "commercial_orders" in restored.sources
    assert restored.sources["buyer_inventory"].payload.startswith(b"Product Name")


def test_republishing_same_sandbox_source_set_is_idempotent():
    repository, organization_id, facility_id = _repository_with_scope()
    state = {
        "active_organization_id": organization_id,
        "active_facility_id": facility_id,
    }
    payload = build_demo_payload(today=date(2026, 8, 17), scale="small")

    first = persist_sandbox_sources(
        state, payload, version="v1", actor="pytest", repository=repository
    )
    second = persist_sandbox_sources(
        state, payload, version="v1", actor="pytest", repository=repository
    )
    history = repository.list_history(organization_id, facility_id, limit=500)

    assert first == second
    active = repository.list_active_sources(organization_id, facility_id)
    assert len(active) == first + 1  # source files + state manifest
    assert len(history) == first + 1
