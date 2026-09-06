"""Runtime bridge from Streamlit session scope to the canonical traceability dispatcher.

This module deliberately does not read the legacy UserIntegrationsStore for
provider-changing work. It reconstructs the same authenticated organization /
facility context used by the web API and asks the modern Metrc context resolver
to prove alpha mode, connection scope and trusted regulatory mapping first.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from modules.coman.db import create_coman_engine


ProviderDispatch = Callable[[str], dict]


@dataclass(frozen=True)
class TraceabilityRuntime:
    ready: bool
    provider: str = "metrc"
    state: str = ""
    license_number: str = ""
    environment: str = "sandbox"
    message: str = ""
    provider_dispatch: ProviderDispatch | None = None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def resolve_streamlit_traceability_runtime(state: Mapping[str, Any]) -> TraceabilityRuntime:
    organization_id = _clean(state.get("active_organization_id"))
    facility_id = _clean(state.get("active_facility_id"))
    user_id = _clean(state.get("auth_user_id"))
    role = _clean(state.get("auth_user_role")) or ("admin" if state.get("is_admin") else "user")
    data_mode = _clean(state.get("data_mode")) or "Uploads"

    if not organization_id or not facility_id:
        return TraceabilityRuntime(False, message="Choose an organization and facility before provider dispatch.")
    if not user_id:
        return TraceabilityRuntime(
            False,
            message="The legacy Streamlit identity has no canonical user id; provider writes remain disabled.",
        )

    try:
        from backend.app.auth import RequestContext
        from backend.app.config import get_settings
        from backend.app.services.metrc_context import resolve_metrc_context

        context = RequestContext(
            user_id=user_id,
            organization_id=organization_id,
            facility_id=facility_id,
            role=role,
            data_mode=data_mode,
        )
        _service, metrc = resolve_metrc_context(create_coman_engine(), get_settings(), context)
    except Exception as exc:
        return TraceabilityRuntime(
            False,
            message=f"Canonical traceability runtime is unavailable: {type(exc).__name__}.",
        )

    dispatch = metrc.provider_dispatch if callable(getattr(metrc, "provider_dispatch", None)) else None
    ready = bool(
        metrc.configured
        and str(metrc.status or "").casefold() == "connected"
        and metrc.trusted_mapping
        and str(metrc.environment or "").casefold() == "sandbox"
        and dispatch is not None
    )
    return TraceabilityRuntime(
        ready=ready,
        state=str(metrc.state or ""),
        license_number=str(metrc.license_number or ""),
        environment=str(metrc.environment or "sandbox"),
        message=str(metrc.message or ""),
        provider_dispatch=dispatch if ready else None,
    )
