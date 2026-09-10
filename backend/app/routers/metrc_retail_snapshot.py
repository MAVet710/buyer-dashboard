from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.regulatory.service import RegulatoryMappingService
from services.metrc_evaluation_sales import SALES_EVALUATION_ACTIONS
from services.metrc_workspace_snapshot import MetrcWorkspaceSnapshotService
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_sales_actions import (
    GovernedMetrcSalesActionService,
    MetrcSalesActionError,
    PROMOTED_SALES_ACTIONS,
    sales_confirmation_token,
)
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc


router = APIRouter()
RESOURCES = ("sales_receipts", "sales_deliveries")
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}
SalesOperation = Literal[
    "sales_receipt_create",
    "sales_receipt_update",
    "sales_receipt_delete",
    "sales_delivery_create",
    "sales_delivery_update",
    "sales_delivery_complete",
]


class SalesActionRequest(BaseModel):
    operation_type: SalesOperation
    payload: dict[str, Any]
    reason: str = Field(default="Controlled Metrc sales action", min_length=3, max_length=255)


class SalesActionExecute(SalesActionRequest):
    confirmation_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=32, max_length=128)


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


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow controlled Metrc sales changes.")


def _action_metrc(context: RequestContext, engine: Engine, settings: Settings):
    require_facility_capability(context, engine, "retail")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="retail",
    )
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    if str(metrc.state or "").strip().upper() != "MA" or str(metrc.environment or "").strip().casefold() != "sandbox":
        raise HTTPException(
            409,
            "Promoted sales writes are currently restricted to the verified Massachusetts Metrc sandbox.",
        )
    return metrc


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


@router.get("/regulatory-actions/status")
def retail_regulatory_action_status(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    require_facility_capability(context, engine, "retail")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="retail",
    )
    jurisdiction = str(metrc.state or "").strip().upper()
    environment = str(metrc.environment or "").strip().casefold()
    ready = bool(metrc.configured and metrc.trusted_mapping and jurisdiction == "MA" and environment == "sandbox")
    return {
        "ready": ready,
        "provider": "metrc",
        "jurisdiction_code": jurisdiction,
        "environment": environment,
        "license_number": str(metrc.license_number or "").strip(),
        "promoted_actions": sorted(PROMOTED_SALES_ACTIONS) if ready else [],
        "documentation_source": "https://api-ma.metrc.com/Documentation",
        "execution_host": "sandbox-api-ma.metrc.com" if ready else "",
        "message": (
            "Current Massachusetts Metrc v2 sales contracts are available through the governed sandbox workflow."
            if ready
            else str(metrc.message or "This facility remains on its current local sales workflow.")
        ),
        "execution_boundary": (
            "Every provider write is exact-license scoped, human confirmed, idempotent in the global ledger, and requires fresh exact Metrc readback before verification."
            if ready
            else "Local sales workflows remain available; provider writes stay disabled."
        ),
    }


@router.post("/regulatory-actions/preview")
def preview_retail_regulatory_action(
    payload: SalesActionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _action_metrc(context, engine, settings)
    service = GovernedMetrcSalesActionService(engine)
    try:
        prepared = service.prepare(
            operation_type=payload.operation_type,
            payload=payload.payload,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
        )
        confirmation_id = str(uuid4())
        token = sales_confirmation_token(
            prepared=prepared,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            confirmation_id=confirmation_id,
        )
        spec = SALES_EVALUATION_ACTIONS[prepared["operation_type"]]
        return {
            "ready": True,
            "operation_type": prepared["operation_type"],
            "summary": prepared["summary"],
            "confirmation_id": confirmation_id,
            "confirmation_token": token,
            "compliance_evidence": {
                "method": spec.method,
                "path": spec.path,
                "license_number": metrc.license_number,
                "environment": metrc.environment,
                "provider_request_body": prepared["provider_request_body"],
                "documentation_source": "https://api-ma.metrc.com/Documentation",
            },
            "message": "Review the business values before confirming. Any payload or facility-context change invalidates this confirmation.",
        }
    except MetrcSalesActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/regulatory-actions/execute")
def execute_retail_regulatory_action(
    payload: SalesActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _action_metrc(context, engine, settings)
    try:
        return GovernedMetrcSalesActionService(engine).execute(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
            operation_type=payload.operation_type,
            payload=payload.payload,
            confirmation_id=payload.confirmation_id,
            confirmation_token=payload.confirmation_token,
            reason=payload.reason,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
        )
    except MetrcSalesActionError as exc:
        raise HTTPException(422, str(exc)) from exc
