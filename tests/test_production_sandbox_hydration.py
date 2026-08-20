from __future__ import annotations

from types import SimpleNamespace

from services import sandbox_market_runtime as runtime


def test_post_context_hydration_seeds_missing_durable_surfaces(monkeypatch):
    state = {}
    organization = SimpleNamespace(id="org-sbx", slug="dev-sandbox")
    facility = SimpleNamespace(id="fac-sbx", code="SANDBOX")
    calls = []

    monkeypatch.setattr(
        runtime,
        "market_sandbox_readiness",
        lambda engine, organization_id, facility_id: {
            "version": runtime.SANDBOX_MARKET_VERSION,
            "ready": False,
            "counts": {"production": 0},
            "missing": ["production"],
        },
    )

    def fake_seed(engine, organization_id, facility_id, *, actor, state):
        calls.append((organization_id, facility_id, actor))
        return {
            "version": runtime.SANDBOX_MARKET_VERSION,
            "ready": True,
            "counts": {"production": 3},
            "missing": [],
        }

    monkeypatch.setattr(runtime, "seed_market_sandbox", fake_seed)

    result = runtime.ensure_market_sandbox_after_context(
        state,
        organization=organization,
        facility=facility,
        actor="dev",
        engine=object(),
    )

    assert result["ready"] is True
    assert calls == [("org-sbx", "fac-sbx", "dev")]
    assert state["demo_sandbox_market_readiness"]["counts"]["production"] == 3
    assert state["_sandbox_market_seed_scope"].startswith("org-sbx|fac-sbx|")
    assert "_sandbox_market_seed_error" not in state


def test_post_context_hydration_verifies_ready_state_without_reseeding(monkeypatch):
    state = {}
    organization = SimpleNamespace(id="org-sbx", slug="dev-sandbox")
    facility = SimpleNamespace(id="fac-sbx", code="SANDBOX")

    monkeypatch.setattr(
        runtime,
        "market_sandbox_readiness",
        lambda engine, organization_id, facility_id: {
            "version": runtime.SANDBOX_MARKET_VERSION,
            "ready": True,
            "counts": {"production": 2, "extraction": 2},
            "missing": [],
        },
    )

    def should_not_seed(*args, **kwargs):
        raise AssertionError("ready sandbox should not be reseeded")

    monkeypatch.setattr(runtime, "seed_market_sandbox", should_not_seed)

    result = runtime.ensure_market_sandbox_after_context(
        state,
        organization=organization,
        facility=facility,
        actor="dev",
        engine=object(),
    )

    assert result["ready"] is True
    assert state["demo_sandbox_market_readiness"]["counts"]["production"] == 2


def test_post_context_hydration_never_seeds_real_tenant(monkeypatch):
    state = {}
    organization = SimpleNamespace(id="org-real", slug="real-customer")
    facility = SimpleNamespace(id="fac-real", code="MAIN")

    def should_not_query(*args, **kwargs):
        raise AssertionError("real tenant must never use sandbox parity runtime")

    monkeypatch.setattr(runtime, "market_sandbox_readiness", should_not_query)
    monkeypatch.setattr(runtime, "seed_market_sandbox", should_not_query)

    result = runtime.ensure_market_sandbox_after_context(
        state,
        organization=organization,
        facility=facility,
        actor="admin",
        engine=object(),
    )

    assert result["ready"] is True
    assert result["skipped"] is True
    assert state == {}
