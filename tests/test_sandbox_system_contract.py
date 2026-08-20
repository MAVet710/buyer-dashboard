from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Base, Facility, Organization, Product
from services.demo_data import build_demo_payload
from services.sandbox_system_contract import (
    CORE_SYSTEM_REQUIREMENTS,
    MARKET_SYSTEM_REQUIREMENTS,
    PLATFORM_CONTROL_SURFACES,
    SANDBOX_DATA_MODE,
    SESSION_SYSTEM_REQUIREMENTS,
    core_sandbox_readiness,
    ensure_full_sandbox_contract,
    force_sandbox_operational_sources,
    is_dev_role,
    rebuild_core_sandbox,
    session_sandbox_system_readiness,
)


def _session_state_from_payload() -> dict:
    payload = build_demo_payload(date(2026, 8, 20), scale="small")
    state = {
        "auth_user_role": "dev",
        "demo_company_profile": dict(payload["company_profile"]),
        "demo_catalog_df": payload["catalog"].copy(),
        "demo_budget_df": payload["budget"].copy(),
        "demo_upload_catalog": dict(payload["uploads"]),
        "inv_raw_df": payload["inventory"].copy(),
        "active_inventory_df": payload["inventory"].copy(),
        "sales_raw_df": payload["sales"].copy(),
        "active_sales_df": payload["sales"].copy(),
        "detail_cached_df": payload["detail"].copy(),
        "detail_product_cached_df": payload["detail_product"].copy(),
        "delivery_manifest_df": payload["manifest"].copy(),
        "delivery_sales_df": payload["sales"].copy(),
        "compliance_sources_df": payload["compliance"].copy(),
        "demo_nomenclature_catalog_df": payload["nomenclature_catalog"].copy(),
        "demo_nomenclature_manifest_df": payload["nomenclature_manifest"].copy(),
        "demo_commercial_partners_df": payload["commercial_partners"].copy(),
        "demo_commercial_orders_df": payload["commercial_orders"].copy(),
        "demo_commercial_order_lines_df": payload["commercial_order_lines"].copy(),
        "demo_production_orders_df": payload["production_orders_export"].copy(),
        "demo_production_machines_df": payload["production_machines_export"].copy(),
        "demo_production_crew_df": payload["production_crew_export"].copy(),
        "ecc_inventory_log": payload["extraction_inventory"].copy(),
        "ecc_run_log": payload["extraction_runs"].copy(),
        "ecc_client_jobs": payload["extraction_jobs"].copy(),
        "white_label_package_plan": list(payload["white_label"]["white_label_package_plan"]),
        "data_mode": "🔴 Dutchie Live",
    }
    return state


def _stale_core_sandbox():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        organization = Organization(name="DEV Sandbox", slug="dev-sandbox", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Sandbox Facility",
            code="SANDBOX",
            timezone_name="America/New_York",
            active=True,
        )
        session.add(facility)
        session.flush()
        # Reproduce the production failure mode: some old core data exists, so
        # the legacy seed used to treat the sandbox as already complete.
        session.add(
            Product(
                organization_id=organization.id,
                sku="STALE-ONLY",
                name="Old partial sandbox product",
                item_type="finished_good",
                base_unit="unit",
                unit_cost=1.0,
                retail_price=4.0,
                active=True,
            )
        )
        org_id, facility_id = organization.id, facility.id
    return engine, org_id, facility_id


def test_full_sandbox_is_strictly_dev_only():
    assert is_dev_role("dev") is True
    assert is_dev_role("DEV") is True
    assert is_dev_role("admin") is False
    assert is_dev_role("buyer") is False

    state = {"auth_user_role": "admin", "data_mode": "🔴 Dutchie Live"}
    result = ensure_full_sandbox_contract(
        state,
        organization=SimpleNamespace(id="org", slug="dev-sandbox"),
        facility=SimpleNamespace(id="fac", code="SANDBOX"),
        role="admin",
        actor="admin",
        engine=object(),
    )
    assert result["skipped"] is True
    assert state["data_mode"] == "🔴 Dutchie Live"


def test_dev_sandbox_forces_operational_sources_off_dutchie_live():
    state = _session_state_from_payload()
    force_sandbox_operational_sources(state)
    assert state["data_mode"] == SANDBOX_DATA_MODE
    assert state["flat_nav_data_mode"] == SANDBOX_DATA_MODE
    assert state["mobile_flat_nav_data_mode"] == SANDBOX_DATA_MODE
    assert state["_sandbox_live_operational_sources_blocked"] is True

    report = session_sandbox_system_readiness(state)
    assert report["ready"] is True, report
    assert report["missing"] == []


def test_every_user_facing_operational_system_has_a_declared_sandbox_source():
    declared = (
        set(SESSION_SYSTEM_REQUIREMENTS)
        | set(CORE_SYSTEM_REQUIREMENTS)
        | set(MARKET_SYSTEM_REQUIREMENTS)
    )
    expected = {
        "Operations Home",
        "Inventory",
        "Products / Product Master",
        "Inventory Audits",
        "Slow Movers",
        "MA Flower Equivalency",
        "Buying Recommendations",
        "Delivery Performance",
        "Purchase Orders",
        "Buying Budget",
        "Orders & Fulfillment",
        "Co-Man Production",
        "Extraction / Run 360",
        "White Label / Repack",
        "Sales & Category Trends",
        "Compliance Q&A",
        "Product Name Mapper",
        "Data Hub",
        "Switch to Buyer Dash",
        "Production Control",
        "Wholesale + Finance",
        "Doobie Actions",
        "Benchmarks",
        "Design Partner",
        "Traceability",
    }
    assert expected.issubset(declared)
    assert {
        "Admin Tools",
        "AI & METRC Integrations",
        "METRC Integrations",
        "Location Settings",
    }.issubset(set(PLATFORM_CONTROL_SURFACES))


def test_stale_partial_core_sandbox_self_upgrades_to_current_complete_seed():
    engine, org_id, facility_id = _stale_core_sandbox()
    before = core_sandbox_readiness(engine, org_id, facility_id)
    assert before["ready"] is False
    assert before["counts"]["product_boms"] == 0
    assert before["counts"]["material_reservations"] == 0

    state = {
        "auth_user_role": "dev",
        "demo_dataset_scale": "small",
        "demo_as_of_date": date(2026, 8, 20),
        "demo_company_seed": 710,
        "demo_catalog_seed": 811,
        "demo_history_seed": 912,
        "demo_problem_set": [],
    }
    rebuild_core_sandbox(engine, state, actor="dev-test")
    after = core_sandbox_readiness(engine, org_id, facility_id)

    assert after["ready"] is True, after
    assert after["counts"]["product_boms"] > 0
    assert after["counts"]["bom_components"] > 0
    assert after["counts"]["material_reservations"] > 0
    assert after["counts"]["production_actuals"] > 0
    assert after["counts"]["inventory_audits"] >= 2
    assert after["counts"]["facility_machines"] > 0
    assert after["counts"]["crew_availability"] > 0
    assert after["counts"]["commercial_orders"] > 0
    assert after["counts"]["trade_partners"] > 0
