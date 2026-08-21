"""Populate Purchasing from the active Buyer Dash tenant after hydration."""
from __future__ import annotations

from functools import wraps
from typing import Any, MutableMapping

from services.purchasing_context import prepare_purchasing_context


PURCHASING_SCOPE_KEYS = (
    "purchasing_ready_df",
    "purchasing_budget_df",
    "purchasing_delivery_ready",
    "purchasing_context_readiness",
    "purchasing_context_reporting_days",
    "purchasing_context_source",
    "_purchasing_context_error",
)


def _clear_purchasing_scope(state: MutableMapping[str, Any]) -> None:
    for key in PURCHASING_SCOPE_KEYS:
        state.pop(key, None)


def install_purchasing_context_runtime() -> None:
    """Attach purchasing preparation to the authenticated tenant boundary.

    The wrapper intentionally runs after whichever hydration wrapper is already
    installed (including DEV Sandbox parity). That guarantees Purchasing sees
    the same inventory/sales/Product Master context as the rest of the app.
    """
    from modules.authentication import access_context

    original = access_context.hydrate_selected_context
    if getattr(original, "_purchasing_context_wrapper", False):
        return

    @wraps(original)
    def hydrated_with_purchasing(
        state: MutableMapping[str, Any],
        *,
        organization: Any,
        facility: Any,
        role: str,
    ) -> tuple[bool, str]:
        scope = (
            f"{str(getattr(organization, 'id', '') or '')}|"
            f"{str(getattr(facility, 'id', '') or '')}"
        )
        previous_scope = str(state.get("_purchasing_context_scope") or "")
        if previous_scope and previous_scope != scope:
            _clear_purchasing_scope(state)
        state["_purchasing_context_scope"] = scope

        hydrated, message = original(
            state,
            organization=organization,
            facility=facility,
            role=role,
        )
        # Even if a non-fatal durable extension is unavailable, the active
        # inventory/sales cache may still be sufficient for Purchasing. Never
        # make navigating to Purchasing depend on visiting Inventory first.
        try:
            report = prepare_purchasing_context(state)
            state["purchasing_context_readiness"] = report
            if report.get("ready"):
                state.pop("_purchasing_context_error", None)
            else:
                state["_purchasing_context_error"] = str(
                    report.get("reason") or "Purchasing data is not ready."
                )
        except Exception as exc:
            state["_purchasing_context_error"] = f"{type(exc).__name__}: {exc}"
        return hydrated, message

    hydrated_with_purchasing._purchasing_context_wrapper = True
    access_context.hydrate_selected_context = hydrated_with_purchasing
