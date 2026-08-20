"""Bind full DEV Sandbox parity to the authenticated tenant-hydration boundary."""
from __future__ import annotations

from functools import wraps
from typing import Any, MutableMapping

from modules.coman.db import create_coman_engine
from services.sandbox_market_seed import _install_reset_guard
from services.sandbox_scope_guard import SANDBOX_SCOPE_MARKER
from services.sandbox_system_contract import (
    ensure_full_sandbox_contract,
    is_dev_role,
    is_dev_sandbox_scope,
)


def install_sandbox_market_hydration_runtime(st: Any) -> None:
    """Verify/self-heal all DEV Sandbox systems after tenant context is known."""
    # Reset safety can be installed before auth because it only changes how the
    # canonical sandbox reset orders FK cleanup. Data seeding itself happens
    # only in the authenticated DEV-only hook below.
    _install_reset_guard()

    from modules.authentication import access_context

    original = access_context.hydrate_selected_context
    if getattr(original, "_sandbox_market_hydration_wrapper", False):
        return

    @wraps(original)
    def hydrated_with_full_sandbox_parity(
        state: MutableMapping[str, Any],
        *,
        organization: Any,
        facility: Any,
        role: str,
    ) -> tuple[bool, str]:
        sandbox_scope = bool(
            is_dev_role(role) and is_dev_sandbox_scope(organization, facility)
        )
        # The legacy living-demo hydration happens inside the original function,
        # so publish the verified scope marker before calling it. Clear the
        # marker first for every other tenant/role to prevent synthetic leakage
        # when a DEV user moves between the sandbox and a real organization.
        if sandbox_scope:
            state[SANDBOX_SCOPE_MARKER] = True
        else:
            state.pop(SANDBOX_SCOPE_MARKER, None)

        hydrated, message = original(
            state,
            organization=organization,
            facility=facility,
            role=role,
        )

        # Real tenants and non-DEV roles never enter seed/repair logic even if
        # stale session flags happen to survive elsewhere in Streamlit state.
        if not sandbox_scope:
            return hydrated, message

        actor = str(
            state.get("auth_username")
            or state.get("admin_user")
            or state.get("user_user")
            or state.get("auth_user_id")
            or role
            or "dev"
        )
        try:
            report = ensure_full_sandbox_contract(
                state,
                organization=organization,
                facility=facility,
                role=role,
                actor=actor,
                engine=create_coman_engine(),
            )
        except Exception as exc:
            detail = (
                "DEV Sandbox could not reach full system parity: "
                f"{type(exc).__name__}: {exc}"
            )
            state["_sandbox_system_contract_error"] = detail
            return False, detail

        if not report.get("ready"):
            detail = str(
                state.get("_sandbox_system_contract_error")
                or "DEV Sandbox system parity is incomplete."
            )
            return False, detail

        readiness_message = (
            f"DEV Sandbox ready: {int(report.get('ready_count') or 0)}/"
            f"{int(report.get('system_count') or 0)} operational systems use sandbox data."
        )
        return True, message or readiness_message

    hydrated_with_full_sandbox_parity._sandbox_market_hydration_wrapper = True
    access_context.hydrate_selected_context = hydrated_with_full_sandbox_parity
