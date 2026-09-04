from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from modules.integrations.models import IntegrationProviderSnapshot, IntegrationSyncState
from modules.traceability.object_links import TraceabilityObjectLink
from ..auth import RequestContext, get_request_context
from ..database import get_engine


router = APIRouter(prefix="/regulatory-detail", tags=["regulatory-detail"])


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age_seconds(value: datetime | None) -> int | None:
    if value is None:
        return None
    seen = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds()))


def _provider_candidates(provider: str) -> tuple[str, ...]:
    name = str(provider or "metrc").strip().casefold()
    if name == "metrc":
        # DEV fixture syncs use metrc_sandbox while authenticated sandbox and
        # production mappings use metrc. Environment remains a separate identity.
        return ("metrc", "metrc_sandbox")
    return (name,)


def _snapshot_payload(row: IntegrationProviderSnapshot | None) -> dict[str, Any] | None:
    if row is None:
        return None
    raw = _json_object(row.raw_payload_json)
    normalized = _json_object(row.normalized_payload_json)
    return {
        "id": row.id,
        "provider": row.provider,
        "environment": row.environment,
        "resource": row.resource,
        "external_id": row.external_id,
        "provider_label": row.provider_label,
        "present": bool(row.present),
        "snapshot_run_id": row.snapshot_run_id,
        "fingerprint": row.fingerprint,
        "last_seen_at": _iso(row.last_seen_at),
        "age_seconds": _age_seconds(row.last_seen_at),
        "normalized_provider_record": normalized,
        "raw_provider_record": raw,
    }


def _sync_payload(row: IntegrationSyncState | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "status": row.status,
        "environment": row.environment,
        "cursor": row.cursor,
        "last_started_at": _iso(row.last_started_at),
        "last_completed_at": _iso(row.last_completed_at),
        "last_success_at": _iso(row.last_success_at),
        "last_error": row.last_error,
        "records_seen": int(row.records_seen or 0),
        "records_written": int(row.records_written or 0),
    }


def _link_payload(row: TraceabilityObjectLink) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "jurisdiction": row.jurisdiction,
        "environment": row.environment,
        "license_number": row.license_number,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "provider_resource": row.provider_resource,
        "provider_id": row.provider_id,
        "provider_label": row.provider_label,
        "status": row.status,
        "verified_at": _iso(row.verified_at),
        "last_seen_at": _iso(row.last_seen_at),
        "mismatch_reason": row.mismatch_reason,
    }


def _latest_snapshot(
    session: Session,
    *,
    organization_id: str,
    facility_id: str,
    provider: str,
    environment: str,
    resource: str,
    external_id: str,
) -> IntegrationProviderSnapshot | None:
    return session.scalar(
        select(IntegrationProviderSnapshot)
        .where(
            IntegrationProviderSnapshot.organization_id == organization_id,
            IntegrationProviderSnapshot.facility_id == facility_id,
            IntegrationProviderSnapshot.provider.in_(_provider_candidates(provider)),
            IntegrationProviderSnapshot.environment == environment,
            IntegrationProviderSnapshot.resource == resource,
            IntegrationProviderSnapshot.external_id == external_id,
        )
        .order_by(desc(IntegrationProviderSnapshot.last_seen_at))
        .limit(1)
    )


def _latest_sync_state(
    session: Session,
    *,
    organization_id: str,
    facility_id: str,
    provider: str,
    environment: str,
    resource: str,
) -> IntegrationSyncState | None:
    return session.scalar(
        select(IntegrationSyncState)
        .where(
            IntegrationSyncState.organization_id == organization_id,
            IntegrationSyncState.facility_id == facility_id,
            IntegrationSyncState.provider.in_(_provider_candidates(provider)),
            IntegrationSyncState.environment == environment,
            IntegrationSyncState.resource == resource,
        )
        .order_by(desc(IntegrationSyncState.last_success_at), desc(IntegrationSyncState.last_completed_at))
        .limit(1)
    )


@router.get("/local/{entity_type}/{entity_id}")
def local_regulatory_detail(
    entity_type: str,
    entity_id: str,
    provider: str = Query(default="metrc"),
    environment: str = Query(default=""),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Resolve exact provider truth for one local DoobieLogic object.

    This endpoint is local-database only. It never contacts Metrc. It exposes the
    exact identity link, current-provider membership, normalized record, lossless
    raw record, sync evidence, and reconciliation state for compliance/detail UIs.
    """

    local_type = str(entity_type or "").strip().casefold()
    local_id = str(entity_id or "").strip()
    provider_name = str(provider or "metrc").strip().casefold()
    env = str(environment or "").strip().casefold()
    if not local_type or not local_id:
        raise HTTPException(422, "Entity type and ID are required.")
    if env and env not in {"sandbox", "production"}:
        raise HTTPException(422, "Environment must be sandbox or production.")

    with Session(engine) as session:
        statement = select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.organization_id == context.organization_id,
            TraceabilityObjectLink.facility_id == context.facility_id,
            TraceabilityObjectLink.provider == provider_name,
            TraceabilityObjectLink.entity_type == local_type,
            TraceabilityObjectLink.entity_id == local_id,
        )
        if env:
            statement = statement.where(TraceabilityObjectLink.environment == env)
        links = list(session.scalars(statement.order_by(desc(TraceabilityObjectLink.last_seen_at))))

        entries: list[dict[str, Any]] = []
        for link in links:
            snapshot = _latest_snapshot(
                session,
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                provider=link.provider,
                environment=link.environment,
                resource=link.provider_resource,
                external_id=link.provider_id,
            )
            sync = _latest_sync_state(
                session,
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                provider=link.provider,
                environment=link.environment,
                resource=link.provider_resource,
            )
            entries.append(
                {
                    "identity": _link_payload(link),
                    "current_snapshot": _snapshot_payload(snapshot),
                    "sync": _sync_payload(sync),
                    "reconciliation_required": link.status == "reconciliation_required",
                    "current_in_provider": bool(snapshot and snapshot.present),
                }
            )

    return {
        "provider": provider_name,
        "entity_type": local_type,
        "entity_id": local_id,
        "network_request_made": False,
        "linked": bool(entries),
        "entries": entries,
    }


@router.get("/provider/{resource}/{external_id}")
def provider_regulatory_detail(
    resource: str,
    external_id: str,
    provider: str = Query(default="metrc"),
    environment: str = Query(default=""),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Read one current/last-seen provider-owned object without inventing local history."""

    resource_name = str(resource or "").strip().casefold()
    external = str(external_id or "").strip()
    provider_name = str(provider or "metrc").strip().casefold()
    env = str(environment or "").strip().casefold()
    if not resource_name or not external:
        raise HTTPException(422, "Provider resource and external ID are required.")
    if env and env not in {"sandbox", "production"}:
        raise HTTPException(422, "Environment must be sandbox or production.")

    with Session(engine) as session:
        statement = select(IntegrationProviderSnapshot).where(
            IntegrationProviderSnapshot.organization_id == context.organization_id,
            IntegrationProviderSnapshot.facility_id == context.facility_id,
            IntegrationProviderSnapshot.provider.in_(_provider_candidates(provider_name)),
            IntegrationProviderSnapshot.resource == resource_name,
            IntegrationProviderSnapshot.external_id == external,
        )
        if env:
            statement = statement.where(IntegrationProviderSnapshot.environment == env)
        snapshot = session.scalar(statement.order_by(desc(IntegrationProviderSnapshot.last_seen_at)).limit(1))
        if snapshot is None:
            raise HTTPException(404, "Provider object was not found in this facility's synchronized regulatory snapshot.")
        sync = _latest_sync_state(
            session,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider=provider_name,
            environment=snapshot.environment,
            resource=snapshot.resource,
        )
        link = session.scalar(
            select(TraceabilityObjectLink)
            .where(
                TraceabilityObjectLink.organization_id == context.organization_id,
                TraceabilityObjectLink.facility_id == context.facility_id,
                TraceabilityObjectLink.provider == provider_name,
                TraceabilityObjectLink.environment == snapshot.environment,
                TraceabilityObjectLink.provider_resource == snapshot.resource,
                TraceabilityObjectLink.provider_id == snapshot.external_id,
            )
            .limit(1)
        )

    return {
        "provider": provider_name,
        "network_request_made": False,
        "current_in_provider": bool(snapshot.present),
        "reconciliation_required": bool(link and link.status == "reconciliation_required"),
        "identity": _link_payload(link) if link is not None else None,
        "current_snapshot": _snapshot_payload(snapshot),
        "sync": _sync_payload(sync),
    }
