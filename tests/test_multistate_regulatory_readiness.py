import pytest

from modules.regulatory import (
    DOCUMENTATION_PENDING_JURISDICTIONS,
    GENERIC_EVALUATION_APPROVED,
    PRODUCTION_WRITE_APPROVED,
    jurisdiction_readiness,
    list_jurisdiction_readiness,
    require_production_write_approved,
    require_sandbox_execution_ready,
)


def test_every_registered_market_has_truthful_release_readiness():
    rows = list_jurisdiction_readiness()
    assert len(rows) >= 29
    assert len({row["code"] for row in rows}) == len(rows)
    assert all(row["known_market"] and row["production_host_verified"] for row in rows)
    assert all(row["safety"]["documentation_is_not_permission"] for row in rows)
    assert all(row["safety"]["sandbox_success_is_not_regulator_approval"] for row in rows)


def test_only_provider_verified_sandbox_deployments_are_execution_ready():
    ma = jurisdiction_readiness("MA")
    assert ma["documentation_verified"] is True
    assert ma["sandbox_host_verified"] is True
    assert ma["release_stage"] == "sandbox_ready_for_evidence"
    assert require_sandbox_execution_ready("MA")["code"] == "MA"

    for code in ("CA", "CO", "MI", "OR", "NY"):
        row = jurisdiction_readiness(code)
        assert row["documentation_verified"] is True
        assert row["sandbox_host_verified"] is False
        assert row["release_stage"] == "documentation_verified"
        with pytest.raises(ValueError, match="sandbox API deployment"):
            require_sandbox_execution_ready(code)


def test_documentation_pending_states_cannot_skip_direct_api_verification():
    for code in DOCUMENTATION_PENDING_JURISDICTIONS:
        row = jurisdiction_readiness(code)
        assert row["documentation_verified"] is False
        assert row["release_stage"] == "market_known"
        with pytest.raises(ValueError, match="Official API documentation"):
            require_sandbox_execution_ready(code)


def test_regulator_and_production_approval_can_never_be_inferred_from_code_or_sandbox():
    assert GENERIC_EVALUATION_APPROVED == frozenset()
    assert PRODUCTION_WRITE_APPROVED == frozenset()
    ma = jurisdiction_readiness("MA")
    assert ma["evaluation_approved"] is False
    assert ma["production_write_approved"] is False
    assert ma["safety"]["production_writes_default_locked"] is True
    with pytest.raises(ValueError, match="Production regulatory writes are not release-approved"):
        require_production_write_approved("MA")


def test_unknown_market_fails_closed():
    row = jurisdiction_readiness("ZZ")
    assert row["known_market"] is False
    assert row["release_stage"] == "unknown_market"
    with pytest.raises(ValueError, match="not verified"):
        require_sandbox_execution_ready("ZZ")
