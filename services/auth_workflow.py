"""Framework-light authentication session workflow helpers."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping


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
    state["_db_hydrated_username"] = ""
    state["_admin_fail_count"] = 0
    state["_user_fail_count"] = 0
    state["_admin_lockout_until"] = None
    state["_user_lockout_until"] = None


def clear_authenticated_session(state: MutableMapping) -> None:
    for key, value in {
        "is_admin": False,
        "admin_user": None,
        "user_authenticated": False,
        "user_user": None,
        "auth_user_id": None,
        "auth_user_role": None,
        "auth_organization_id": None,
        "active_organization_id": None,
        "active_facility_id": None,
        "auth_must_change_password": False,
        "_db_hydrated_username": "",
    }.items():
        state[key] = value
