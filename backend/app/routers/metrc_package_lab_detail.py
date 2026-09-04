from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent
from modules.integrations.provider_snapshot import IntegrationProviderSnapshotRepository
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_receiving import fetch_metrc_lab_results
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_context import resolve_metrc_context


router = APIRouter(prefix="/regulatory-detail", tags=["regulatory-detail"])


def _lab_resource(provider_package_id: str) -> str:
    token = hashlib.sha256(str(provider_package_id or "").strip().encode("utf-8")).hexdigest()[:24]
    return f"lab_results_package_{token}"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age_seconds(value: datetime | None) -> int | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - aware.astimezone(timezone.utc)).total_seconds()))


def _package_link(
    session: Session,
    *,
    organization_id: str,
    facility_id: str,
    entity_id: str,
    environment: str = "",
) -> TraceabilityObjectLink | None:
    statement = select(TraceabilityObjectLink).where(
        TraceabilityObjectLink.organization_id == organization_id,
        TraceabilityObjectLink.facility_id == facility_id,
        TraceabilityObjectLink.provider == "metrc",
        TraceabilityObjectLink.entity_type == "inventory_lot",
        TraceabilityObjectLink.entity_id == entity_id,
        TraceabilityObjectLink.provider_resource == "packages",
    )
    if environment:
        statement = statement.where(TraceabilityObjectLink.environment == environment)
    rows = list(session.scalars(statement.order_by(desc(TraceabilityObjectLink.last_seen_at))))
    if len(rows) > 1 and not environment:
        raise HTTPException(
            409,
            "This package has Metrc identities in more than one environment. Select the exact sandbox or production environment.",
        )
    return rows[0] if rows else None


def _cached_payload(
    *,
    engine: Engine,
    context: RequestContext,
    link: TraceabilityObjectLink | None,
    network_request_made: bool,
) -> dict[str, Any]:
    if link is None:
        return {
            "provider": "metrc",
            "linked": False,
            "network_request_made": network_request_made,
            "provider_package_id": "",
            "provider_package_label": "",
            "environment": "",
            "license_number": "",
            "identity_status": "unlinked",
            "last_synced_at": None,
            "age_seconds": None,
            "result_count": 0,
            "results": [],
        }

    resource = _lab_resource(link.provider_id)
    rows = IntegrationProviderSnapshotRepository(engine).current(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        provider="metrc",
        resources=(resource,),
        environment=link.environment,
        limit=5000,
    )
    parsed: list[dict[str, Any]] = []
    newest: datetime | None = None
    for row in rows:
        try:
            value = json.loads(row.raw_payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            parsed.append(value)
        if newest is None or row.last_seen_at > newest:
            newest = row.last_seen_at
    return {
        "provider": "metrc",
        "linked": True,
        "network_request_made": network_request_made,
        "provider_package_id": link.provider_id,
        "provider_package_label": link.provider_label,
        "environment": link.environment,
        "license_number": link.license_number,
        "identity_status": link.status,
        "last_synced_at": _iso(newest),
        "age_seconds": _age_seconds(newest),
        "result_count": len(parsed),
        "results": parsed,
    }


@router.get("/local/inventory_lot/{entity_id}/lab-results")
def cached_package_lab_results(
    entity_id: str,
    environment: str = Query(default=""),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Return the last package-specific Metrc lab verification without a provider call."""

    env = str(environment or "").strip().casefold()
    if env and env not in {"sandbox", "production"}:
        raise HTTPException(422, "Environment must be sandbox or production.")
    with Session(engine) as session:
        link = _package_link(
            session,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_id=str(entity_id or "").strip(),
            environment=env,
        )
    return _cached_payload(engine=engine, context=context, link=link, network_request_made=False)


@router.get("/local/inventory_lot/{entity_id}/lab-results/live")
def live_package_lab_results(
    entity_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Explicitly verify package-scoped lab results through the trusted Metrc mapping.

    This is the only networked path in this package lab panel. Successful complete
    responses are cached under a package-specific resource key so one package's
    lab refresh can never mark another package's results absent.
    """

    try:
        _configuration_service, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not metrc.configured:
        raise HTTPException(422, metrc.message or "Configure the Metrc connection before live lab verification.")
    if not metrc.trusted_mapping:
        raise HTTPException(409, "Verify the exact Metrc facility/license mapping before live lab verification.")

    with Session(engine) as session:
        link = _package_link(
            session,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_id=str(entity_id or "").strip(),
            environment=metrc.environment,
        )
    if link is None:
        raise HTTPException(409, "This DoobieLogic inventory lot has no exact Metrc package identity in the active environment.")
    if (
        link.jurisdiction != metrc.state.upper()
        or link.license_number != metrc.license_number
        or link.environment != metrc.environment
    ):
        raise HTTPException(409, "The package identity does not match the active trusted Metrc jurisdiction/license/environment scope.")

    result = fetch_metrc_lab_results(
        state=metrc.state,
        user_api_key=metrc.user_api_key,
        integrator_api_key=metrc.integrator_api_key,
        license_number=metrc.license_number,
        package_id=link.provider_id,
        environment=metrc.environment,
        timeout_seconds=20,
    )
    if not result.get("ok"):
        provider_status = int(result.get("http_status") or 0)
        status_code = provider_status if provider_status in {400, 403, 429} else 502
        raise HTTPException(status_code, str(result.get("message") or "Metrc package lab verification failed."))

    records = [dict(row) for row in result.get("lab_results") or [] if isinstance(row, dict)]
    resource = _lab_resource(link.provider_id)
    run_id = str(uuid.uuid4())
    repository = IntegrationProviderSnapshotRepository(engine)
    complete = not bool(result.get("truncated"))
    if complete:
        cache = repository.replace(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider="metrc",
            environment=metrc.environment,
            resource=resource,
            run_id=run_id,
            records=records,
        )
    else:
        cache = repository.upsert_delta(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider="metrc",
            environment=metrc.environment,
            resource=resource,
            run_id=run_id,
            records=records,
        )

    with Session(engine) as session, session.begin():
        session.add(AuditEvent(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            entity_type="inventory_lot",
            entity_id=entity_id,
            action="metrc_package_lab_results_verified",
            actor=context.user_id,
            changes_json=json.dumps(
                {
                    "provider_package_id": link.provider_id,
                    "provider_package_label": link.provider_label,
                    "environment": metrc.environment,
                    "license_number": metrc.license_number,
                    "result_count": len(records),
                    "page_count": int(result.get("page_count") or 1),
                    "complete": complete,
                    "cache": cache,
                },
                sort_keys=True,
            ),
        ))

    payload = _cached_payload(engine=engine, context=context, link=link, network_request_made=True)
    payload.update(
        {
            "provider_verified": True,
            "complete": complete,
            "page_count": int(result.get("page_count") or 1),
            "cache": cache,
        }
    )
    return payload
