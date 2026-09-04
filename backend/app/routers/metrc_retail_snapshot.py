from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from modules.regulatory.service import RegulatoryMappingService
from services.metrc_workspace_snapshot import MetrcWorkspaceSnapshotService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine


router = APIRouter()
RESOURCES = ("sales_receipts", "sales_deliveries")


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
            "Multiple active Metrc mappings exist for this retail facility. Resolve the exact facility/license mapping before using synchronized sales state.",
        )
    return rows[0]


def _source(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("source")
    return nested if isinstance(nested, dict) else row


def _value(row: dict[str, Any], *keys: str) -> str:
    source = _source(row)
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            value = source.get(key)
        if value not in (None, "") and str(value).strip():
            return str(value).strip()
    return ""


def _rows(resource: dict[str, Any], *, limit: int = 100) -> dict[str, Any]:
    records = [dict(row) for row in resource.get("records") or [] if isinstance(row, dict)]
    return {
        "resource": resource.get("resource"),
        "status": resource.get("status"),
        "complete": bool(resource.get("complete")),
        "count": len(records),
        "last_synced_at": resource.get("last_synced_at"),
        "records_truncated": len(records) > limit,
        "records": [
            {
                "provider_id": _value(row, "provider_id", "Id", "ID", "id"),
                "status": _value(row, "status", "Status", "State"),
                "receipt_number": _value(row, "ReceiptNumber", "SalesReceiptNumber", "ExternalReceiptNumber", "Number"),
                "delivery_number": _value(row, "DeliveryNumber", "SalesDeliveryNumber", "Number"),
                "recorded_at": _value(row, "SalesDateTime", "DeliveryDateTime", "CreatedDateTime", "LastModified"),
                "total": _value(row, "TotalPrice", "Total", "Amount"),
            }
            for row in records[:limit]
        ],
    }


@router.get("/regulatory-snapshot")
def retail_regulatory_snapshot_from_sync(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Load current synchronized Metrc retail sales state without a provider call."""

    require_facility_capability(context, engine, "retail")
    mapping = _mapping(engine, context)
    if mapping is None:
        return {
            "configured": False,
            "ready": False,
            "provider": "metrc",
            "scope": "retail",
            "read_only": True,
            "source": "integration_provider_snapshots",
            "network_request_made": False,
            "message": "No verified Metrc facility mapping is active for this retail facility.",
            "summary": {"active_sales_receipt_count": 0, "active_sales_delivery_count": 0},
            "resources": {},
        }

    snapshot = MetrcWorkspaceSnapshotService(engine).read(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        environment=mapping.environment,
        resources=RESOURCES,
    )
    receipts = snapshot["resources"]["sales_receipts"]
    deliveries = snapshot["resources"]["sales_deliveries"]
    ready = bool(receipts["complete"] or deliveries["complete"])
    return {
        "configured": True,
        "ready": ready,
        "provider": "metrc",
        "scope": "retail",
        "jurisdiction_code": mapping.jurisdiction_code,
        "license_number": mapping.license_number,
        "environment": mapping.environment,
        "read_only": True,
        "source": "integration_provider_snapshots",
        "network_request_made": False,
        "last_synced_at": snapshot.get("last_synced_at"),
        "message": (
            "Last synchronized Metrc retail sales state loaded locally. No provider request was made."
            if ready
            else "This verified retail facility has not completed a synchronized sales receipt or delivery snapshot yet."
        ),
        "summary": {
            "active_sales_receipt_count": receipts["count"],
            "active_sales_delivery_count": deliveries["count"],
        },
        "resources": {
            "sales_receipts": _rows(receipts),
            "sales_deliveries": _rows(deliveries),
        },
    }
