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
        "delivery_manifest",
        "compliance_sources",
        "extraction_inventory",
        "extraction_runs",
        "extraction_jobs",
    }.issubset(first["uploads"])


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
