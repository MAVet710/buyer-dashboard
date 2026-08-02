from __future__ import annotations

from datetime import date

import pandas as pd

from services import demo_data


def _state() -> dict:
    return {
        "auth_user_role": "dev",
        "demo_dataset_scale": "small",
        "demo_as_of_date": date(2026, 7, 22),
    }


def test_demo_payload_is_deterministic_and_complete():
    first = demo_data.build_demo_payload(
        date(2026, 7, 22),
        scale="small",
        company_seed=710,
        catalog_seed=811,
        history_seed=912,
    )
    second = demo_data.build_demo_payload(
        date(2026, 7, 22),
        scale="small",
        company_seed=710,
        catalog_seed=811,
        history_seed=912,
    )

    assert first["scale"] == "small"
    assert len(first["inventory"]) == 28
    assert len(first["sales"]) == 950
    assert first["inventory"].equals(second["inventory"])
    assert first["sales"].equals(second["sales"])
    assert {
        "buyer_inventory",
        "buyer_sales",
        "buyer_extra_sales",
        "buyer_quarantine",
        "delivery_manifest",
        "delivery_sales",
        "compliance_sources",
        "extraction_inventory",
        "extraction_runs",
        "extraction_jobs",
        "nomenclature_catalog",
        "nomenclature_manifest",
        "commercial_partners",
        "commercial_orders",
        "commercial_order_lines",
        "commercial_ledger",
        "production_orders",
        "production_machines",
        "production_crew",
        "purchasing_budget",
    }.issubset(first["uploads"])
    assert set(first["white_label"]["white_label_package_plan"][index]["package_size_g"] for index in range(4)) == {
        3.5,
        7.0,
        14.0,
        28.0,
    }
    assert (first["catalog"]["retail_price"] > first["catalog"]["unit_cost"]).all()
    assert (first["sales"]["Gross Profit"] > 0).all()
    assert (first["extraction_runs"]["gross_profit_usd"] > 0).all()
    assert (first["extraction_runs"]["gross_margin_pct"] >= 31.9).all()
    assert (first["commercial_order_lines"]["Gross Profit"] >= 0).all()
    assert (
        first["commercial_order_lines"]
        .loc[first["commercial_order_lines"]["Gross Profit"] > 0, "Gross Profit"]
        .gt(0)
        .all()
    )


def test_session_seed_preserves_real_upload_and_supports_reset(monkeypatch):
    monkeypatch.setattr(
        demo_data,
        "_seed_coman",
        lambda state, actor, payload, force: (True, ""),
    )
    uploaded = pd.DataFrame([{"SKU": "REAL-1", "Available": 7}])
    state = _state() | {"inv_raw_df": uploaded.copy(), "auth_user_id": "user-1"}

    result = demo_data.ensure_full_app_demo_session(state, actor="God")

    assert result.seeded is True
    assert result.coman_seeded is True
    assert state["inv_raw_df"].equals(uploaded)
    assert not state["sales_raw_df"].empty
    assert len(state["data_hub_import_history"]) == 20
    assert state["_full_app_demo_version"] == demo_data.DEMO_DATA_VERSION

    demo_data.reset_demo_session(state, preserve_auth=True)

    assert state["auth_user_role"] == "dev"
    assert state["auth_user_id"] == "user-1"
    assert "inv_raw_df" not in state
    assert "sales_raw_df" not in state
    assert "_full_app_demo_version" not in state


def test_living_company_advances_and_incident_changes_state(monkeypatch):
    monkeypatch.setattr(
        demo_data,
        "_seed_coman",
        lambda state, actor, payload, force: (True, ""),
    )
    state = _state()
    demo_data.ensure_full_app_demo_session(state, actor="planner")
    original_inventory = state["inv_raw_df"].copy()
    original_sales_rows = len(state["sales_raw_df"])

    advanced = demo_data.advance_demo_company(state, days=30, actor="planner")

    assert advanced.seeded is True
    assert state["demo_as_of_date"] == date(2026, 8, 21)
    assert len(state["sales_raw_df"]) >= original_sales_rows
    assert not state["inv_raw_df"].equals(original_inventory)
    assert "Advanced company 30 days" in state["demo_event_log"][-1]["event"]

    demo_data.inject_demo_problem(state, "Full operational chaos", actor="planner")

    assert state["demo_selected_scenario"] == "Full operational chaos"
    assert {"qa_hold", "failed_coa", "machine_downtime", "negative_margin"}.issubset(
        set(state["demo_problem_set"])
    )
    assert state["_coman_demo_seeded"] is True


def test_every_persona_returns_a_grounded_training_answer(monkeypatch):
    monkeypatch.setattr(
        demo_data,
        "_seed_coman",
        lambda state, actor, payload, force: (True, ""),
    )
    state = _state()
    demo_data.ensure_full_app_demo_session(state, actor="trainer")

    for persona in demo_data.PERSONAS:
        result = demo_data.run_demo_roleplay(
            state,
            persona,
            "What requires attention now?",
        )
        assert result["answer"].strip()
        assert result["mode"]

    assert len(state["demo_training_history"]) == len(demo_data.PERSONAS)


def test_demo_company_is_profitable_with_a_believable_inventory_curve():
    payload = demo_data.build_demo_payload(date(2026, 8, 2), scale="medium")
    product_detail = payload["detail_product"]
    capped_doh = product_detail["daysonhand"].clip(upper=120)

    assert 18 <= float(capped_doh.median()) <= 45
    assert 18 <= float(capped_doh.mean()) <= 50
    assert product_detail["reorderpriority"].astype(str).str.contains("Reorder ASAP").any()
    assert product_detail["reorderpriority"].astype(str).str.contains("Dead Item").sum() <= 6
    assert payload["sales"]["Gross Margin %"].between(25, 75).all()
    assert payload["sales"]["Gross Profit"].gt(0).all()
