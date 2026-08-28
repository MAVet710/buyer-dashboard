from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import Engine

from ..auth import RequestContext, require_facility_capability
from ..config import Settings
from .metrc_context import MetrcContext, resolve_metrc_context


def resolve_trusted_regulatory_metrc(
    *,
    context: RequestContext,
    engine: Engine,
    settings: Settings,
    facility_capability: str,
) -> MetrcContext:
    """Resolve a read-only Metrc context for one exact licensed facility.

    This helper is for regulatory inspection/reconciliation, not inventory
    receiving. It therefore enforces facility capability + exact trusted mapping
    without coupling read access to receiving roles.
    """

    require_facility_capability(context, engine, facility_capability)
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    if not metrc.configured:
        return metrc
    if metrc.status != "connected":
        raise HTTPException(
            status_code=409,
            detail="Validate the Metrc connection for this exact facility before loading live regulatory data.",
        )
    if not metrc.trusted_mapping:
        raise HTTPException(
            status_code=409,
            detail="An administrator must verify the exact Metrc facility, license, jurisdiction, credential, and environment mapping before live regulatory data can load.",
        )
    return metrc
