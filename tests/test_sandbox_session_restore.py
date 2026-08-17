from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.data_hub_repository import DataHubRepository
from services import demo_data
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


def test_fresh_session_restores_sandbox_from_durable_sources(monkeypatch):
    repository, organization_id, facility_id = _repository_with_scope()
    original_state = {
        "active_organization_id": organization_id,
        "active_facility_id": facility_id,
        "demo_company_seed": 710,
        "demo_catalog_seed": 811,
        "demo_history_seed": 912,
        "demo_selected_scenario": "Healthy baseline",
    }
    payload = demo_data.build_demo_payload(today=date(2026, 8, 17), scale="small")
    persist_sandbox_sources(
        original_state,
        payload,
        version=demo_data.DEMO_DATA_VERSION,
        actor="pytest",
        repository=repository,
    )

    fresh_state = {
        "auth_user_role": "dev",
        "user_authenticated": True,
        "active_organization_id": organization_id,
        "active_facility_id": facility_id,
    }
    monkeypatch.setattr(
        demo_data,
        "restore_sandbox_sources",
        lambda state: restore_sandbox_sources(state, repository=repository),
    )
    monkeypatch.setattr(
        demo_data,
        "_seed_coman",
        lambda state, actor, payload, force: (True, ""),
    )

    result = demo_data.ensure_full_app_demo_session(fresh_state, actor="pytest")

    assert result.seeded is True
    assert fresh_state["_sandbox_supabase_restored"] is True
    assert fresh_state["_sandbox_supabase_persisted"] is True
    assert "restored from Supabase" in fresh_state["demo_data_banner"]
    assert not fresh_state["inv_raw_df"].empty
    assert not fresh_state["sales_raw_df"].empty
    assert not fresh_state["ecc_run_log"].empty
    assert not fresh_state["demo_commercial_orders_df"].empty
    assert fresh_state["_cache_inv"]["durable"] is True
    assert fresh_state["_cache_sales"]["durable"] is True
    assert fresh_state["_full_app_demo_version"] == demo_data.DEMO_DATA_VERSION
    assert len(fresh_state["data_hub_import_history"]) == len(payload["uploads"])
