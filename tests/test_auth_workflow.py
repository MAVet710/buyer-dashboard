from datetime import datetime, timedelta, timezone

from services import demo_data
from services.auth_workflow import (
    apply_authenticated_session,
    authenticate_any_role,
    clear_authenticated_session,
    mark_session_activity,
    session_is_expired,
)


def test_authenticate_any_role_identifies_admin_and_standard_accounts():
    def authenticate(username, password, require_admin):
        if username == "God" and require_admin:
            return True, "God"
        if username == "operator" and not require_admin:
            return True, "operator"
        return False, ""

    assert authenticate_any_role(authenticate, "God", "secret") == (True, "God", True)
    assert authenticate_any_role(authenticate, "operator", "secret") == (
        True,
        "operator",
        False,
    )


def test_auth_session_helpers_seed_and_clear_demo_context(monkeypatch):
    seeded = []

    def fake_seed(state, *, actor="demo", force=False, today=None):
        seeded.append((actor, force))
        state["demo_mode_enabled"] = True
        state["_full_app_demo_version"] = demo_data.DEMO_DATA_VERSION

    def fake_reset(state, *, preserve_auth=True, reset_database=False):
        assert preserve_auth is False
        state.pop("_full_app_demo_version", None)
        state.pop("demo_mode_enabled", None)

    monkeypatch.setattr(demo_data, "ensure_full_app_demo_session", fake_seed)
    monkeypatch.setattr(demo_data, "reset_demo_session", fake_reset)

    state = {"auth_user_role": "dev", "active_facility_id": "facility-1"}
    apply_authenticated_session(state, "God", True)

    assert seeded == [("God", False)]
    assert state["is_admin"] is True
    assert state["admin_user"] == "God"
    assert state["demo_mode_enabled"] is True

    clear_authenticated_session(state)

    assert state["is_admin"] is False
    assert state["admin_user"] is None
    assert state["auth_user_role"] is None
    assert state["active_facility_id"] is None
    assert state["demo_mode_enabled"] is False


def test_idle_session_expiration_is_timezone_safe():
    now = datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc)
    state = {}
    mark_session_activity(state, now=now - timedelta(minutes=89))
    assert session_is_expired(state, idle_minutes=90, now=now) is False

    mark_session_activity(state, now=now - timedelta(minutes=91))
    assert session_is_expired(state, idle_minutes=90, now=now) is True


def test_invalid_session_timestamp_fails_closed():
    assert session_is_expired({"auth_last_activity_at": "not-a-date"}) is True
