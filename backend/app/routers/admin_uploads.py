from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import AppUser, AuditEvent, DataHubImport, Facility, utc_now
from modules.integrations.models import IntegrationConfiguration
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/admin", tags=["admin"])
_UPLOAD_TTL_MINUTES = 60


def _require_admin(context: RequestContext) -> None:
    if context.role.casefold() not in {"dev", "admin"}:
        raise HTTPException(403, "Organization administrator access is required.")


def _scope(query, context: RequestContext):
    if context.role.casefold() == "dev":
        return query
    return query.where(DataHubImport.organization_id == context.organization_id)


def _latest_clear(session: Session, context: RequestContext):
    query = select(func.max(AuditEvent.occurred_at)).where(
        AuditEvent.entity_type == "admin_upload_viewer",
        AuditEvent.action == "viewer_cleared",
        AuditEvent.actor == context.user_id,
    )
    if context.role.casefold() != "dev":
        query = query.where(AuditEvent.organization_id == context.organization_id)
    return session.scalar(query)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/uploads")
def list_admin_uploads(
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Mirror the Streamlit 60-minute admin upload viewer without deleting source data.

    React source uploads are durable, so clearing this viewer records a per-admin
    viewer cutoff instead of destroying the files that power the application.
    """
    _require_admin(context)
    cutoff = _aware_utc(utc_now()) - timedelta(minutes=_UPLOAD_TTL_MINUTES)
    with Session(engine) as session:
        cleared_at = _aware_utc(_latest_clear(session, context))
        if cleared_at and cleared_at > cutoff:
            cutoff = cleared_at
        query = select(DataHubImport).where(DataHubImport.created_at >= cutoff)
        query = _scope(query, context)
        rows = list(session.scalars(query.order_by(DataHubImport.created_at.desc()).limit(limit)))
        return {
            "ttl_minutes": _UPLOAD_TTL_MINUTES,
            "uploads": [
                {
                    "ts": row.created_at,
                    "uploader": row.imported_by,
                    "role": row.dataset_label,
                    "filename": row.filename,
                    "upload_id": row.id,
                    "organization_id": row.organization_id,
                    "facility_id": row.facility_id,
                    "size": row.payload_size,
                    "status": row.status,
                }
                for row in rows
            ],
        }


@router.get("/uploads/{upload_id}/download")
def download_admin_upload(
    upload_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_admin(context)
    with Session(engine) as session:
        row = session.get(DataHubImport, upload_id)
        if row is None:
            raise HTTPException(404, "Upload is no longer available.")
        if context.role.casefold() != "dev" and row.organization_id != context.organization_id:
            raise HTTPException(403, "This upload belongs to another organization.")
        try:
            payload = gzip.decompress(bytes(row.payload_compressed))
        except (OSError, EOFError) as exc:
            raise HTTPException(422, "Stored upload could not be read.") from exc
        if len(payload) != int(row.payload_size):
            raise HTTPException(422, "Stored upload failed its integrity check.")
        safe_name = str(row.filename or "upload.bin").replace('"', "")
        return Response(
            payload,
            media_type=row.content_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
        )


@router.post("/uploads/clear")
def clear_admin_upload_viewer(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_admin(context)
    with Session(engine) as session, session.begin():
        session.add(
            AuditEvent(
                organization_id=context.organization_id,
                facility_id=context.facility_id or None,
                entity_type="admin_upload_viewer",
                entity_id=context.user_id,
                action="viewer_cleared",
                actor=context.user_id,
                changes_json=json.dumps({"ttl_minutes": _UPLOAD_TTL_MINUTES}, sort_keys=True),
            )
        )
    return {"cleared": True}


@router.get("/diagnostics")
def admin_diagnostics(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Non-secret operational diagnostics for the Streamlit Admin Tools surface."""
    _require_admin(context)
    with Session(engine) as session:
        users_query = select(func.count()).select_from(AppUser)
        facilities_query = select(func.count()).select_from(Facility).where(Facility.active.is_(True))
        uploads_query = select(func.count()).select_from(DataHubImport)
        integrations_query = select(IntegrationConfiguration)
        if context.role.casefold() != "dev":
            users_query = users_query.where(AppUser.organization_id == context.organization_id)
            facilities_query = facilities_query.where(Facility.organization_id == context.organization_id)
            uploads_query = uploads_query.where(DataHubImport.organization_id == context.organization_id)
            integrations_query = integrations_query.where(
                (IntegrationConfiguration.organization_id == context.organization_id)
                | (IntegrationConfiguration.facility_id.in_(select(Facility.id).where(Facility.organization_id == context.organization_id)))
            )
        integrations = list(session.scalars(integrations_query))
        return {
            "organization_id": context.organization_id,
            "facility_id": context.facility_id,
            "role": context.role,
            "users": int(session.scalar(users_query) or 0),
            "active_facilities": int(session.scalar(facilities_query) or 0),
            "durable_upload_versions": int(session.scalar(uploads_query) or 0),
            "integrations": [
                {
                    "provider": row.provider,
                    "scope_type": row.scope_type,
                    "status": row.status,
                    "facility_id": row.facility_id or "",
                    "secret_hint": row.secret_hint,
                    "last_validated_at": row.last_validated_at,
                    "last_error": row.last_error,
                }
                for row in integrations
            ],
        }
