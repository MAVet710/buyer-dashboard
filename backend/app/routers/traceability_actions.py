from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, InventoryLot
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.action_registry import get_traceability_action, list_traceability_actions
from modules.traceability.global_ledger import GlobalTraceabilityLedger, machine_status
from services.traceability_dispatcher import TraceabilityDispatcher, TraceabilityDispatchError
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/traceability-actions", tags=["traceability-actions"])
DISPATCH_ROLES = {"dev", "admin", "supervisor", "qa"}
INVENTORY_ACTION_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}

# The catalog is the provider-neutral vocabulary shown to operators and Doobie Agent.
# Being present here does not imply that automatic Metrc dispatch is enabled. Provider
# writes still require a separate reviewed write contract and exact tenant/facility scope.
ACTION_CATALOG: dict[str, dict[str, Any]] = {
    action.name: {
        "entity_type": action.entity_type,
        "required": action.required_fields,
        "roles": set(action.roles),
        "class": action.action_class,
    }
    for action in list_traceability_actions()
}


class TraceabilityIntent(BaseModel):
    provider: str = "metrc"
    operation_type: str
    entity_id: str = Field(min_length=1, max_length=255)
    license_number: str = ""
    jurisdiction: str = Field(default="", max_length=16)
    environment: str = Field(default="", max_length=24)
    direction: str = Field(default="outbound", pattern="^(inbound|outbound)$")
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=255)
    idempotency_key: str = Field(min_length=3, max_length=255)
    workflow_id: str = Field(default="", max_length=255)
    client_action_id: str = Field(default="", max_length=255)
    queue_source: str = Field(default="web", pattern="^(web|mobile|offline_replay|workflow|agent)$")
    preview_token: str = Field(default="", max_length=64)


class InventoryMoveIntent(BaseModel):
    lot_id: str = Field(min_length=1, max_length=255)
    destination_location: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="Operational inventory move", min_length=3, max_length=255)
    sync_to_metrc: bool = False


class InventoryHoldIntent(BaseModel):
    lot_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(default="Operational hold", min_length=3, max_length=255)


class ExceptionResolutionIntent(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


def _catalog_row(name: str, *, jurisdiction: str = "", environment: str = "") -> dict[str, Any]:
    action = get_traceability_action(name)
    if action is None:
        raise ValueError(f"Unknown traceability action {name!r}.")
    return action.public(jurisdiction=jurisdiction, environment=environment)


def _preview_token(payload: TraceabilityIntent) -> str:
    document = payload.model_dump(exclude={"preview_token"})
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _preflight(payload: TraceabilityIntent, context: RequestContext, engine: Engine) -> dict[str, Any]:
    action = get_traceability_action(payload.operation_type)
    if action is None:
        raise HTTPException(422, "Unsupported traceability operation type.")
    if context.role.casefold() not in action.roles:
        raise HTTPException(403, "Your role cannot perform this traceability action.")
    provider = payload.provider.strip().casefold()
    blockers: list[dict[str, str]] = []
    if provider not in {"metrc", "biotrack", "other"}:
        blockers.append({"code": "provider_invalid", "message": "Choose a supported traceability provider."})
    environment = payload.environment.strip().casefold()
    if provider in {"metrc", "biotrack"}:
        if not payload.jurisdiction.strip() or not environment or not payload.license_number.strip():
            blockers.append({"code": "facility_mapping_incomplete", "message": "Jurisdiction, environment, and license must be known before this action can run."})
        if environment not in {"sandbox", "production"}:
            blockers.append({"code": "environment_not_verified", "message": "Choose the exact sandbox or production provider environment."})
    missing = [field for field in action.required_fields if payload.payload.get(field) in (None, "", [], {})]
    if missing:
        blockers.append({"code": "input_missing", "message": f"Complete {', '.join(missing)} before confirming."})
    pending = TraceabilityBackofficeRepository(engine).list_transactions(
        context.organization_id,
        context.facility_id,
        statuses=("validated", "queued", "submitted", "accepted", "reconciliation_required"),
        provider=provider,
        entity_type=action.entity_type,
        entity_id=payload.entity_id,
        environment=environment,
        limit=10,
    )
    conflicting = [row for row in pending if row.idempotency_key != payload.idempotency_key]
    if conflicting:
        blockers.append({"code": "conflicting_pending_action", "message": "This object already has a provider action awaiting execution or reconciliation. Resolve it before creating another write."})
    return {
        "ready": not blockers,
        "preview_token": _preview_token(payload),
        "action": action.public(jurisdiction=payload.jurisdiction, environment=environment),
        "summary": {
            "title": action.label,
            "entity": {"type": action.entity_type, "id": payload.entity_id},
            "affected_count": max(1, len(payload.payload.get("entity_ids") or payload.payload.get("plant_ids") or payload.payload.get("package_ids") or [])),
            "environment": environment,
            "license_number": payload.license_number,
            "verification": action.verification_resource,
        },
        "blockers": blockers,
        "revalidate_on_execute": True,
    }


def _json_value(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {"unparseable": True}


def _operator_status(status: str) -> str:
    return {
        "requested": "Pending",
        "validated": "Pending",
        "queued": "Pending",
        "submitted": "Awaiting Verification",
        "accepted": "Provider Accepted",
        "verified": "Synced",
        "rejected": "Failed",
        "reconciliation_required": "Reconciliation Required",
        "cancelled": "Blocked",
    }.get(status, "Needs Review")


def _transaction_view(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "jurisdiction": row.jurisdiction,
        "environment": row.environment,
        "organization_id": row.organization_id,
        "facility_id": row.facility_id,
        "license_number": row.license_number,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "operation": row.operation_type,
        "direction": row.direction,
        "provider_reference": row.external_reference,
        "provider_tag": row.external_tag,
        "correlation_id": row.correlation_id,
        "source": row.source,
        "status": row.status,
        "machine_status": machine_status(row),
        "operator_status": _operator_status(row.status),
        "attempt_count": row.attempt_count,
        "last_attempt_at": row.last_attempt_at,
        "next_attempt_at": row.next_attempt_at,
        "retry_eligible": row.retry_eligible,
        "latest_error": row.error_message or row.error_code,
        "error_classification": row.error_classification,
        "reconciliation_state": row.reconciliation_state,
        "resolution_state": row.resolution_state,
        "resolution_note": row.resolution_note,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at,
        "parent_entity": {"type": row.parent_entity_type, "id": row.parent_entity_id} if row.parent_entity_id else None,
        "related_entities": _json_value(row.related_entities_json),
        "local_state": _json_value(row.local_state_json),
        "provider_state": _json_value(row.provider_state_json),
        "readback_result": _json_value(row.readback_result_json),
        "mismatch_reason": row.mismatch_reason,
        "reconciliation_evidence": _json_value(row.reconciliation_evidence_json),
        "actor": row.requested_by,
        "requested_at": row.requested_at,
        "submitted_at": row.submitted_at,
        "completed_at": row.completed_at,
    }


def _require_inventory_action_role(context: RequestContext) -> None:
    if context.role.casefold() not in INVENTORY_ACTION_ROLES:
        raise HTTPException(403, "Your role cannot change inventory operational state.")


def _inventory_lot(session: Session, context: RequestContext, lot_id: str) -> InventoryLot:
    lot = session.get(InventoryLot, lot_id)
    if not lot or lot.organization_id != context.organization_id or lot.facility_id != context.facility_id:
        raise HTTPException(404, "Inventory package was not found in the active facility.")
    return lot


def _audit_inventory_action(session: Session, context: RequestContext, lot: InventoryLot, action: str, changes: dict[str, Any]) -> None:
    session.add(AuditEvent(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        entity_type="inventory_lot",
        entity_id=lot.id,
        action=action,
        actor=context.user_id,
        changes_json=json.dumps(changes, sort_keys=True),
    ))


@router.get("/catalog")
def action_catalog(
    jurisdiction: str = Query(default="", max_length=16),
    environment: str = Query(default="", max_length=24),
    context: RequestContext = Depends(get_request_context),
):
    role = context.role.casefold()
    return {
        "actions": [
            _catalog_row(action.name, jurisdiction=jurisdiction, environment=environment)
            for action in list_traceability_actions()
            if role in action.roles and action.catalog_visible
        ],
        "automatic_dispatch_operations": [
            action.name
            for action in list_traceability_actions()
            if action.public(jurisdiction=jurisdiction, environment=environment)["dispatch_enabled"]
        ],
        "dispatch_roles": sorted(DISPATCH_ROLES),
        "move_semantics": {
            "move": "Change location within the same licensed facility.",
            "transfer": "Move inventory between licensed facilities through the transfer/manifest workflow.",
        },
        "execution_boundary": "Validated intents enter the durable provider-neutral queue. A separately authorized provider dispatch is required; accepted still does not mean reconciled/verified.",
    }


@router.post("/preview")
def preview_action(
    payload: TraceabilityIntent,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Return an operator summary and deterministic blockers without a provider write."""
    return _preflight(payload, context, engine)


@router.post("/inventory/move")
def move_inventory(
    payload: InventoryMoveIntent,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Move a package between operational locations inside the same facility.

    This is deliberately distinct from an inter-facility transfer. Newly reviewed
    Metrc package-location writes remain fail-closed until the deterministic
    provider payload/readback contract is promoted, so a caller cannot silently
    claim a state-system move that DoobieLogic has not actually verified.
    """
    _require_inventory_action_role(context)
    destination = payload.destination_location.strip()
    if not destination:
        raise HTTPException(422, "Choose a destination room or location.")
    if payload.sync_to_metrc:
        raise HTTPException(
            409,
            "Metrc package Move is documented but automatic execution is still locked pending exact payload/readback verification. Complete the move in Metrc or use DoobieLogic-only operational location until that contract is promoted.",
        )
    with Session(engine) as session, session.begin():
        lot = _inventory_lot(session, context, payload.lot_id)
        previous = str(lot.location_code or "").strip()
        if previous.casefold() == destination.casefold():
            return {
                "lot_id": lot.id,
                "package_id": lot.compliance_package_id or lot.lot_code,
                "previous_location": previous,
                "location": previous,
                "status": str(lot.status or ""),
                "metrc_status": "not_requested",
                "changed": False,
            }
        lot.location_code = destination
        _audit_inventory_action(session, context, lot, "inventory_location_moved", {
            "previous_location": previous,
            "destination_location": destination,
            "reason": payload.reason.strip(),
            "state_system_sync": False,
        })
        session.flush()
        return {
            "lot_id": lot.id,
            "package_id": lot.compliance_package_id or lot.lot_code,
            "previous_location": previous,
            "location": destination,
            "status": str(lot.status or ""),
            "metrc_status": "not_requested",
            "changed": True,
        }


@router.post("/inventory/hold")
def hold_inventory(
    payload: InventoryHoldIntent,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_inventory_action_role(context)
    with Session(engine) as session, session.begin():
        lot = _inventory_lot(session, context, payload.lot_id)
        previous = str(lot.status or "available")
        if previous.casefold() == "hold":
            return {"lot_id": lot.id, "status": "hold", "changed": False}
        lot.status = "hold"
        _audit_inventory_action(session, context, lot, "inventory_hold_applied", {
            "previous_status": previous,
            "status": "hold",
            "reason": payload.reason.strip(),
        })
        session.flush()
        return {"lot_id": lot.id, "status": "hold", "changed": True}


@router.post("/inventory/release-hold")
def release_inventory_hold(
    payload: InventoryHoldIntent,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_inventory_action_role(context)
    with Session(engine) as session, session.begin():
        lot = _inventory_lot(session, context, payload.lot_id)
        previous = str(lot.status or "available")
        if previous.casefold() != "hold":
            raise HTTPException(409, "Only an operational Hold can be released here. QA quarantine, failed testing, and other regulatory states must use their controlled release workflow.")
        lot.status = "available"
        _audit_inventory_action(session, context, lot, "inventory_hold_released", {
            "previous_status": previous,
            "status": "available",
            "reason": payload.reason.strip(),
        })
        session.flush()
        return {"lot_id": lot.id, "status": "available", "changed": True}


@router.post("/queue", status_code=201)
def queue_action(payload: TraceabilityIntent, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    preview = _preflight(payload, context, engine)
    if preview["blockers"]:
        first = preview["blockers"][0]
        status_code = 409 if first["code"] == "conflicting_pending_action" else 422
        raise HTTPException(status_code, first["message"])
    if payload.preview_token and payload.preview_token != preview["preview_token"]:
        raise HTTPException(409, "This action changed after preview. Review the current action again before confirming it.")
    operation = payload.operation_type.strip().casefold()
    spec = ACTION_CATALOG.get(operation)
    if not spec:
        raise HTTPException(422, "Unsupported traceability operation type.")
    if context.role.casefold() not in spec["roles"]:
        raise HTTPException(403, "Your role cannot queue this traceability operation.")
    provider = payload.provider.strip().casefold()
    if provider not in {"metrc", "biotrack", "other"}:
        raise HTTPException(422, "Provider must be metrc, biotrack, or other.")
    if provider in {"metrc", "biotrack"}:
        if not payload.jurisdiction.strip() or not payload.environment.strip() or not payload.license_number.strip():
            raise HTTPException(422, "Jurisdiction, environment, and license number are required for state-system actions.")
        if payload.environment.strip().casefold() not in {"sandbox", "production"}:
            raise HTTPException(422, "State-system environment must be sandbox or production.")
    missing = [field for field in spec["required"] if payload.payload.get(field) in (None, "", [], {})]
    if missing:
        raise HTTPException(422, f"Traceability payload is missing required field(s): {', '.join(missing)}")
    repository = TraceabilityBackofficeRepository(engine)
    related_entities = [
        {"type": field.removesuffix("_ids").removesuffix("_id"), "id": str(value)}
        for field, values in payload.payload.items()
        if field.endswith(("_id", "_ids"))
        for value in (values if isinstance(values, list) else [values])
        if value not in (None, "")
    ]
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
            jurisdiction=payload.jurisdiction.strip().upper(),
            environment=payload.environment.strip().casefold(),
            direction=payload.direction,
            request_payload=payload.payload,
            reason=payload.reason,
            correlation_id=payload.workflow_id.strip() or payload.client_action_id.strip() or payload.idempotency_key,
            source=f"typed_action_{payload.queue_source}",
            external_tag=str(payload.payload.get("tag") or payload.payload.get("package_tag") or ""),
            related_entities=related_entities,
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


@router.get("/ledger")
def traceability_ledger(
    statuses: str = Query(default="", max_length=255),
    provider: str = Query(default="", max_length=24),
    entity_type: str = Query(default="", max_length=64),
    entity_id: str = Query(default="", max_length=255),
    environment: str = "",
    limit: int = Query(default=250, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    repository = TraceabilityBackofficeRepository(engine)
    rows = repository.list_transactions(
        context.organization_id,
        context.facility_id,
        statuses=tuple(value.strip() for value in statuses.split(",") if value.strip()),
        provider=provider,
        entity_type=entity_type,
        entity_id=entity_id,
        environment=environment,
        limit=limit,
    )
    return {
        "summary": repository.summary(context.organization_id, context.facility_id, environment=environment),
        "transactions": [_transaction_view(row) for row in rows],
    }


@router.get("/ledger/exceptions")
def traceability_exceptions(
    environment: str = Query(default="", max_length=24),
    entity_type: str = Query(default="", max_length=64),
    before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    repository = GlobalTraceabilityLedger(engine)
    rows = repository.list_exceptions(
        context.organization_id, context.facility_id,
        environment=environment, entity_type=entity_type, before=before, limit=limit,
    )
    return {
        "healthy": not rows,
        "count": len(rows),
        "exceptions": [_transaction_view(row) for row in rows],
        "next_before": rows[-1].requested_at if len(rows) == limit else None,
    }


@router.get("/entities/{entity_type}/{entity_id}/history")
def traceability_entity_history(
    entity_type: str,
    entity_id: str,
    environment: str = Query(default="", max_length=24),
    limit: int = Query(default=50, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    repository = GlobalTraceabilityLedger(engine)
    rows = repository.entity_history(
        context.organization_id, context.facility_id, entity_type, entity_id,
        environment=environment, limit=limit,
    )
    inbound = next((row for row in rows if row.direction == "inbound" and machine_status(row) == "succeeded"), None)
    outbound = next((row for row in rows if row.direction == "outbound" and machine_status(row) == "succeeded"), None)
    return {
        "entity": {"type": entity_type, "id": entity_id},
        "current_state": machine_status(rows[0]) if rows else "not_linked",
        "unresolved_exception_count": sum(machine_status(row) in {"conflict", "failed_retryable", "failed_permanent"} for row in rows),
        "last_successful_inbound": inbound.completed_at if inbound else None,
        "last_successful_outbound": outbound.completed_at if outbound else None,
        "events": [_transaction_view(row) for row in rows],
    }


@router.post("/ledger/{transaction_id}/retry")
def retry_traceability_exception(
    transaction_id: str,
    intent: ExceptionResolutionIntent,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in DISPATCH_ROLES:
        raise HTTPException(403, "Supervisor, QA, Admin, or DEV approval is required to retry a regulatory action.")
    try:
        row = GlobalTraceabilityLedger(engine).prepare_retry(
            context.organization_id, context.facility_id, transaction_id,
            actor=context.user_id, reason=intent.note,
        )
        return _transaction_view(row)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/ledger/{transaction_id}/resolve")
def resolve_traceability_exception(
    transaction_id: str,
    intent: ExceptionResolutionIntent,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in DISPATCH_ROLES:
        raise HTTPException(403, "Supervisor, QA, Admin, or DEV approval is required to resolve a regulatory exception.")
    try:
        row = GlobalTraceabilityLedger(engine).resolve_exception(
            context.organization_id, context.facility_id, transaction_id,
            actor=context.user_id, note=intent.note,
        )
        return _transaction_view(row)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/ledger/{transaction_id}")
def traceability_ledger_detail(
    transaction_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    repository = TraceabilityBackofficeRepository(engine)
    try:
        row = repository.get_transaction(context.organization_id, context.facility_id, transaction_id)
        detail = _transaction_view(row)
        detail["attempts"] = [
            {
                "attempt_number": attempt.attempt_number,
                "http_status": attempt.http_status,
                "error": attempt.error_message or attempt.error_code,
                "request": _json_value(attempt.request_payload_json),
                "response": _json_value(attempt.response_payload_json),
                "started_at": attempt.started_at,
                "completed_at": attempt.completed_at,
            }
            for attempt in repository.list_attempts(context.organization_id, context.facility_id, transaction_id)
        ]
        detail["events"] = [
            {
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor": event.actor,
                "reason": event.reason,
                "source": event.source,
                "occurred_at": event.occurred_at,
            }
            for event in repository.list_status_events(context.organization_id, context.facility_id, transaction_id)
        ]
        return detail
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


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
