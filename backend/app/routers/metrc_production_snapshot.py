from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.regulatory.service import RegulatoryMappingService
from services.metrc_workspace_snapshot import MetrcWorkspaceSnapshotService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine


router = APIRouter()
RESOURCES = ("packages", "processing_jobs")


def _mapping(engine: Engine, context: RequestContext):
    rows = [
        row
        for row in RegulatoryMappingService(engine).list_for_facility(context.organization_id, context.facility_id)
        if row.provider == "metrc" and row.active
    ]
    if not rows:
        return None
    if len(rows) > 1:
        raise HTTPException(
            409,
            "Multiple active Metrc mappings exist for this production facility. Resolve the exact facility/license mapping before using synchronized manufacturing state.",
        )
    return rows[0]


def _source(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("source")
    return nested if isinstance(nested, dict) else row


def _first(row: dict[str, Any], *keys: str) -> str:
    source = _source(row)
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            value = source.get(key)
        if value not in (None, "") and str(value).strip():
            return str(value).strip()
    return ""


def _processing_view(resource: dict[str, Any], *, limit: int = 100) -> dict[str, Any]:
    records = [dict(row) for row in resource.get("records") or [] if isinstance(row, dict)]
    projected = []
    for row in records[:limit]:
        projected.append({
            "provider_id": _first(row, "provider_id", "Id", "ID", "id"),
            "name": _first(row, "name", "Name", "JobTypeName", "ProcessingJobTypeName"),
            "status": _first(row, "status", "Status", "State"),
            "job_type": _first(row, "JobTypeName", "ProcessingJobTypeName", "TypeName"),
            "location": _first(row, "LocationName", "RoomName"),
            "package_label": _first(row, "PackageLabel", "SourcePackageLabel", "OutputPackageLabel"),
            "started_at": _first(row, "StartDate", "StartedDateTime", "StartDateTime", "CreatedDateTime"),
            "last_modified": _first(row, "last_modified", "LastModified", "LastModifiedDateTime"),
        })
    return {
        "resource": resource.get("resource"),
        "status": resource.get("status"),
        "complete": bool(resource.get("complete")),
        "count": len(records),
        "last_synced_at": resource.get("last_synced_at"),
        "records_truncated": len(records) > limit,
        "records": projected,
    }


def _package_view(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource": resource.get("resource"),
        "status": resource.get("status"),
        "complete": bool(resource.get("complete")),
        "count": int(resource.get("count") or 0),
        "last_synced_at": resource.get("last_synced_at"),
    }


@router.get("/production/regulatory/manufacturing-snapshot")
def manufacturing_regulatory_snapshot_from_sync(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Load the last synchronized manufacturing state without contacting Metrc."""

    require_facility_capability(context, engine, "production")
    mapping = _mapping(engine, context)
    if mapping is None:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "scope": "manufacturing",
            "read_only": True,
            "source": "integration_provider_snapshots",
            "network_request_made": False,
            "message": "No verified Metrc facility mapping is active for this production facility.",
            "summary": {"active_package_count": 0, "active_processing_job_count": 0},
            "resources": {},
        }

    snapshot = MetrcWorkspaceSnapshotService(engine).read(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        environment=mapping.environment,
        resources=RESOURCES,
    )
    packages = snapshot["resources"]["packages"]
    processing = snapshot["resources"]["processing_jobs"]
    ready = bool(packages["complete"] or processing["complete"])
    return {
        "configured": True,
        "ready": ready,
        "provider": "metrc",
        "scope": "manufacturing",
        "jurisdiction_code": mapping.jurisdiction_code,
        "license_number": mapping.license_number,
        "environment": mapping.environment,
        "read_only": True,
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "last_synced_at": snapshot.get("last_synced_at"),
        "message": (
            "Last synchronized Metrc manufacturing state loaded locally. No provider request was made."
            if ready
            else "This verified production facility has not completed a synchronized package or processing-job snapshot yet."
        ),
        "summary": {
            "active_package_count": packages["count"],
            "active_processing_job_count": processing["count"],
        },
        "resources": {
            "packages": _package_view(packages),
            "processing_jobs": _processing_view(processing),
        },
        "live_verification_endpoint": "/api/v1/inventory/production/regulatory/manufacturing",
    }
