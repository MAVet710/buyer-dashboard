"""Scope guard for the canonical living DEV Sandbox.

Synthetic full-company data may load only when both the authenticated role is
DEV and tenant hydration has positively identified ``dev-sandbox / SANDBOX``.
This prevents a developer inspecting a real customer tenant from inheriting demo
session data merely because their account has elevated privileges.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SANDBOX_SCOPE_MARKER = "_dev_sandbox_scope_active"


def sandbox_demo_enabled_for_state(state: Mapping[str, Any]) -> bool:
    return bool(
        str(state.get("auth_user_role") or "").strip().casefold() == "dev"
        and state.get(SANDBOX_SCOPE_MARKER) is True
    )


def install_dev_sandbox_scope_guard() -> None:
    """Narrow the legacy demo gate to authenticated DEV + canonical sandbox scope."""
    from services import demo_data

    current = demo_data.demo_enabled_for_state
    if getattr(current, "_dev_sandbox_scope_only", False):
        return

    sandbox_demo_enabled_for_state._dev_sandbox_scope_only = True
    demo_data.demo_enabled_for_state = sandbox_demo_enabled_for_state
