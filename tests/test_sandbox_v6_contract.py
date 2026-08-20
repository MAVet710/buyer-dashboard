from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.data_hub_repository import DataHubRepository
from services import demo_data
from services.auth_workflow import apply_authenticated_session
from services.sandbox_persistence import (
    SANDBOX_CONTRACT_VERSION,
    persist_sandbox_sources,
    restore_sandbox_sources,
)


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


def test_all_sandbox_scales_use_exactly_120_days_of_sales():
    for scale in ("small", "medium", "enterprise"):
        payload = demo_data.build_demo_payload(date(2026, 8, 19), scale=scale)
        sales = payload["sales"]
        order_times = pd.to_datetime(sales["Order Time"], errors="raise")
        span = int((order_times.max().normalize() - order_times.min().normalize()).days) + 1

        assert payload["reporting_days"] == 120
        assert span == 120
        assert sales["Report Start"].nunique() == 1
        assert sales["Report End"].nunique() == 1
        assert payload["sandbox_readiness"]["checks"]["retail_sales.120_day_window"] is True


def test_sandbox_contains_finished_retail_and_bulk_production_inventory():
    payload = demo_data.build_demo_payload(date(2026, 8, 19), scale="medium")
    retail = payload["inventory"]
    production = payload["production_inventory"]

    assert not retail.empty
    assert not production.empty
    assert retail["Inventory Class"].eq("Finished Retail").all()
    assert retail["Item Type"].eq("finished_good").all()
    assert retail["Package ID"].astype(str).str.strip().ne("").all()
    assert retail["SKU"].astype(str).str.strip().ne("").all()
    assert retail["COA ID"].astype(str).str.strip().ne("").all()
    assert {"Available", "Reserved", "On Hand Total", "Cost", "Med Price", "Received Date", "Expiration Date"}.issubset(retail.columns)

    assert production["inventory_class"].str.contains("Bulk", case=False, na=False).all()
    assert production["item_type"].eq("cannabis").all()
    assert production["inventory_unit"].eq("g").all()
    assert production["metrc_package_id"].astype(str).str.strip().ne("").all()
    assert {"current_weight_g", "reserved_weight_g", "available_weight_g", "cost_per_g", "lab_status", "storage_location"}.issubset(production.columns)
    assert payload["sandbox_readiness"]["ready"] is True, payload["sandbox_readiness"]["issues"]


def test_supabase_sandbox_contract_persists_production_inventory_and_120_day_sales():
    repository, organization_id, facility_id = _repository_with_scope()
    state = {
        "active_organization_id": organization_id,
        "active_facility_id": facility_id,
        "demo_company_seed": 710,
        "demo_catalog_seed": 811,
        "demo_history_seed": 912,
        "demo_selected_scenario": "Healthy baseline",
    }
    payload = demo_data.build_demo_payload(date(2026, 8, 19), scale="small")

    count = persist_sandbox_sources(
        state,
        payload,
        version=demo_data.DEMO_DATA_VERSION,
        actor="pytest",
        repository=repository,
    )
    restored = restore_sandbox_sources(state, repository=repository)

    assert count >= 22
    assert restored.available is True
    assert restored.manifest["contract_version"] == SANDBOX_CONTRACT_VERSION
    assert restored.manifest["sales_window_days"] == 120
    assert "production_inventory" in restored.sources
    assert "buyer_sales" in restored.sources


def test_login_does_not_seed_unscoped_sandbox_before_tenant_selection():
    state: dict = {"auth_user_role": "dev", "_full_app_demo_version": "stale"}

    apply_authenticated_session(state, "demo-user", True)

    assert "_full_app_demo_version" not in state
    assert "_sandbox_supabase_restored" not in state
    assert "active_organization_id" not in state
    assert "active_facility_id" not in state
