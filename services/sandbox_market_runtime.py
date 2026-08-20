"""Bind durable DEV Sandbox parity to the authenticated tenant-hydration boundary.

The original market sandbox installer ran from ``streamlit_app.py`` before the
selected organization/facility was guaranteed to exist. Core demo hydration is
authoritative in ``access_context.hydrate_selected_context``; this runtime hooks
that boundary so newer durable modules are seeded and verified only after the
canonical DEV Sandbox scope is known.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, MutableMapping

from modules.coman.demo_data import DEMO_FACILITY_CODE, DEMO_ORGANIZATION_SLUG
from modules.coman.db import create_coman_engine
from services.sandbox_market_seed import (
    SANDBOX_MARKET_VERSION,
    install_sandbox_market_runtime,
    market_sandbox_readiness,
    seed_market_sandbox,
)


def _is_dev_sandbox(organization: Any, facility: Any) -> bool:
    return (
        str(getattr(organization, "slug", "") or "").strip().casefold()
        == DEMO_ORGANIZATION_SLUG.casefold()
        and str(getattr(facility, "code", "") or "").strip().casefold()
        == DEMO_FACILITY_CODE.casefold()
    )


def ensure_market_sandbox_after_context(
    state: MutableMapping[str, Any],
    *,
    organization: Any,
    facility: Any,
    actor: str,
    engine: Any | None = None,
) -> dict[str, Any]:
    """Verify then seed durable sandbox surfaces after tenant context is known."""
    if not _is_dev_sandbox(organization, facility):
        return {
            "version": SANDBOX_MARKET_VERSION,
            "ready": True,
            "skipped": True,
            "counts": {},
        }

    organization_id = str(getattr(organization, "id", "") or "").strip()
    facility_id = str(getattr(facility, "id", "") or "").strip()
    if not organization_id or not facility_id:
        raise ValueError("DEV Sandbox context is missing organization/facility IDs.")

    db_engine = engine or create_coman_engine()
    readiness = market_sandbox_readiness(db_engine, organization_id, facility_id)
    if not readiness.get("ready"):
        readiness = seed_market_sandbox(
            db_engine,
            organization_id,
            facility_id,
            actor=actor or "sandbox",
            state=state,
        )

    state["demo_sandbox_market_readiness"] = readiness
    scope = f"{organization_id}|{facility_id}|{SANDBOX_MARKET_VERSION}"
    if readiness.get("ready"):
        state["_sandbox_market_seed_scope"] = scope
        state.pop("_sandbox_market_seed_error", None)
    else:
        missing = readiness.get("missing") or readiness.get("missing_tables") or []
        state["_sandbox_market_seed_error"] = (
            "Durable sandbox parity is incomplete: " + ", ".join(str(item) for item in missing)
        )
    return readiness


def install_sandbox_market_hydration_runtime(st: Any) -> None:
    """Install legacy guards plus a post-hydration seed/verification hook."""
    # Keep the existing reset guard and best-effort early seed. The hook below is
    # the authoritative path because it runs after access context is resolved.
    install_sandbox_market_runtime(st)

    from modules.authentication import access_context

    original = access_context.hydrate_selected_context
    if getattr(original, "_sandbox_market_hydration_wrapper", False):
        return

    @wraps(original)
    def hydrated_with_market_parity(
        state: MutableMapping[str, Any],
        *,
        organization: Any,
        facility: Any,
        role: str,
    ) -> tuple[bool, str]:
        hydrated, message = original(
            state,
            organization=organization,
            facility=facility,
            role=role,
        )
        if not _is_dev_sandbox(organization, facility):
            return hydrated, message

        actor = str(
            state.get("auth_username")
            or state.get("admin_user")
            or state.get("user_user")
            or state.get("auth_user_id")
            or role
            or "sandbox"
        )
        try:
            readiness = ensure_market_sandbox_after_context(
                state,
                organization=organization,
                facility=facility,
                actor=actor,
            )
        except Exception as exc:
            detail = f"Durable DEV Sandbox features could not hydrate: {type(exc).__name__}: {exc}"
            state["_sandbox_market_seed_error"] = detail
            return False, detail

        if not readiness.get("ready"):
            detail = str(state.get("_sandbox_market_seed_error") or "Durable DEV Sandbox parity is incomplete.")
            return False, detail

        if message:
            return hydrated, message
        return True, "DEV Sandbox durable Production Ops features are ready."

    hydrated_with_market_parity._sandbox_market_hydration_wrapper = True
    access_context.hydrate_selected_context = hydrated_with_market_parity
