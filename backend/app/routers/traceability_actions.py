from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.traceability_dispatcher import TraceabilityDispatcher, TraceabilityDispatchError
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/traceability-actions", tags=["traceability-actions"])
DISPATCH_ROLES = {"dev", "admin", "supervisor", "qa"}

ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "package_create": {"entity_type": "package", "required": ("source_ids", "quantity", "unit"), "roles": {"dev", "admin", "supervisor", "operator", "qa"}},
    "package_finish": {"entity_type": "package", "required": (), "roles": {"dev", "admin", "supervisor", "operator", "qa"}},
    "package_adjust": {"entity_type": "package", "required": ("quantity_delta", "unit", "reason"), "roles": {"dev", "admin", "supervisor", "operator", "qa"}},
    "package_split": {"entity_type": "package", "required": ("quantity", "unit"), "roles": {"dev", "admin", "supervisor", "operator"}},
    "package_merge": {"entity_type": "package", "required": ("source_ids",), "roles": {"dev", "admin", "supervisor"}},
    "transfer_create": {"entity_type": "transfer", "required": ("destination_license", "package_ids"), "roles": {"dev", "admin", "supervisor"}},
    "manifest_update": {"entity_type": "transfer", "required": ("manifest_reference",), "roles": {"dev", "admin", "supervisor"}},
    "production_transform": {"entity_type": "production_order", "required": ("input_package_ids", "output_package_ids"), "roles": {"dev", "admin", "planner", "supervisor", "qa"}},
    "sales_report": {"entity_type": "sales_period", "required": ("period_start", "period_end"), "roles": {"dev", "admin", "supervisor"}},
    "lab_test_update": {"entity_type": "package", "required": ("lab_status",), "roles": {"dev", "admin", "supervisor", "qa"}},
    "plant_move": {"entity_type": "plant", "required": ("destination_location",), "roles": {"dev", "admin", "supervisor", "operator"}},
    "plant_harvest": {"entity_type": "harvest", "required": ("plant_ids", "harvest_name"), "roles": {"dev", "admin", "supervisor", "operator"}},
    "waste_record": {"entity_type": "waste", "required": ("quantity", "unit", "reason"), "roles": {"dev", "admin", "supervisor", "operator", "qa"}},
}


class TraceabilityIntent(BaseModel):
    provider: str = "metrc"
    operation_type: str
    entity_id: str = Field(min_length=1, max_length=255)
    license_number: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=255)
    idempotency_key: str = Field(min_length=3, max_length=255)


def _catalog_row(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {"operation_type": name, "entity_type": spec["entity_type"], "required_fields": list(spec["required"]), "roles": sorted(spec["roles"])}


@router.get("/catalog")
def action_catalog(context: RequestContext = Depends(get_request_context)):
    role = context.role.casefold()
    return {
        "actions": [_catalog_row(name, spec) for name, spec in ACTION_CATALOG.items() if role in spec["roles"]],
        "automatic_dispatch_operations": ["package_finish", "package_adjust"],
        "dispatch_roles": sorted(DISPATCH_ROLES),
        "execution_boundary": "Validated intents enter the durable provider-neutral queue. A separately authorized provider dispatch is required; accepted still does not mean reconciled/verified.",
    }


@router.post("/queue", status_code=201)
def queue_action(payload: TraceabilityIntent, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    operation = payload.operation_type.strip().casefold()
    spec = ACTION_CATALOG.get(operation)
    if not spec:
        raise HTTPException(422, "Unsupported traceability operation type.")
    if context.role.casefold() not in spec["roles"]:
        raise HTTPException(403, "Your role cannot queue this traceability operation.")
    provider = payload.provider.strip().casefold()
    if provider not in {"metrc", "biotrack", "other"}:
        raise HTTPException(422, "Provider must be metrc, biotrack, or other.")
    missing = [field for field in spec["required"] if payload.payload.get(field) in (None, "", [], {})]
    if missing:
        raise HTTPException(422, f"Traceability payload is missing required field(s): {', '.join(missing)}")
    repository = TraceabilityBackofficeRepository(engine)
    try:
        row = repository.create_transaction(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            provider=provider,
            operation_type=operation,
            entity_type=spec["entity_type"],
            entity_id=payload.entity_id,
            idempotency_key=payload.idempotency_key,
            actor=context.user_id,
            license_number=payload.license_number,
            request_payload=payload.payload,
            reason=payload.reason,
        )
        if row.status == "requested":
            row = repository.transition_logged(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                transaction_id=row.id,
                new_status="validated",
                actor=context.user_id,
                reason="Typed traceability intent passed deterministic schema validation.",
                source="system",
            )
        if row.status == "validated":
            row = repository.transition_logged(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                transaction_id=row.id,
                new_status="queued",
                actor=context.user_id,
                reason="Validated traceability intent queued for separately authorized provider dispatch.",
                source="system",
            )
        return {
            "id": row.id,
            "provider": row.provider,
            "operation_type": row.operation_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "status": row.status,
            "idempotency_key": row.idempotency_key,
            "provider_execution": "queued_not_assumed_successful",
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{transaction_id}/dispatch")
def dispatch_action(
    transaction_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in DISPATCH_ROLES:
        raise HTTPException(403, "Supervisor, QA, Admin, or DEV approval is required to dispatch a state-system mutation.")
    if not str(settings.integration_encryption_key or "").strip():
        raise HTTPException(503, "Integration credential encryption is not configured.")
    try:
        return TraceabilityDispatcher(
            engine,
            encryption_key=settings.integration_encryption_key,
            metrc_integrator_api_key=settings.metrc_integrator_key,
        ).dispatch(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            transaction_id=transaction_id,
            actor=context.user_id,
        )
    except TraceabilityDispatchError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
