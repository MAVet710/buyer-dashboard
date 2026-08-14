"""Framework-light authentication session workflow helpers."""
from __future__ import annotations

from collections.abc import Callable, MutableMapping
from datetime import datetime, timedelta, timezone

Authenticator = Callable[[str, str, bool], tuple[bool, str]]


def authenticate_any_role(authenticate: Authenticator, username: str, password: str) -> tuple[bool, str, bool]:
    """Try privileged then standard access and return whether the account is administrative."""
    authenticated, account_name = authenticate(username, password, True)
    if authenticated:
        return True, account_name, True
    authenticated, account_name = authenticate(username, password, False)
    return authenticated, account_name, False


def apply_authenticated_session(state: MutableMapping, account_name: str, is_admin: bool) -> None:
    state["is_admin"] = bool(is_admin)
    state["admin_user"] = account_name if is_admin else None
    state["user_authenticated"] = not is_admin
    state["user_user"] = account_name if not is_admin else None
    if is_admin and not state.get("auth_user_role"):
        state["auth_user_role"] = "admin"
    state["_db_hydrated_username"] = ""
    state["_admin_fail_count"] = 0
    state["_user_fail_count"] = 0
    state["_admin_lockout_until"] = None
    state["_user_lockout_until"] = None
    mark_session_activity(state)
    try:
        from services.demo_data import ensure_full_app_demo_session

        ensure_full_app_demo_session(state, actor=account_name)
    except Exception:
        # Authentication must never fail merely because optional demo data could not seed.
        pass


def mark_session_activity(state: MutableMapping, *, now: datetime | None = None) -> None:
    moment = now or datetime.now(timezone.utc)
    state["auth_last_activity_at"] = moment.astimezone(timezone.utc).isoformat()


def session_is_expired(
    state: MutableMapping,
    *,
    idle_minutes: int = 90,
    now: datetime | None = None,
) -> bool:
    """Return whether an authenticated session exceeded its idle window."""

    raw = state.get("auth_last_activity_at")
    if not raw:
        return False
    try:
        last_activity = datetime.fromisoformat(str(raw))
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    current = now or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc) - last_activity.astimezone(timezone.utc) > timedelta(
        minutes=max(1, int(idle_minutes))
    )


def clear_authenticated_session(state: MutableMapping) -> None:
    try:
        from services.demo_data import reset_demo_session

        reset_demo_session(state, preserve_auth=False)
    except Exception:
        pass
    for key, value in {
        "is_admin": False,
        "admin_user": None,
        "user_authenticated": False,
        "user_user": None,
        "auth_user_id": None,
        "auth_user_role": None,
        "auth_organization_id": None,
        "active_organization_id": None,
        "active_organization_name": "",
        "active_facility_id": None,
        "active_facility_name": "",
        "auth_must_change_password": False,
        "_db_hydrated_username": "",
        "auth_last_activity_at": None,
        "demo_mode_enabled": False,
    }.items():
        state[key] = value
