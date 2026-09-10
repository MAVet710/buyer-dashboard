from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.inventory_transfers.service import InventoryTransferService
from modules.regulatory.metrc_process_readiness import MetrcTransferReadinessService
from services.metrc_evaluation_transfers import TRANSFER_WRITE_EVALUATION_ACTIONS
from ..auth import RequestContext, get_request_context, require_any_facility_capability, require_inventory_operation_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..schemas.inventory_transfers import (
    InventoryTransferCancel,
    InventoryTransferDispatchCreate,
    InventoryTransferItem,
    InventoryTransferReceiveLine,
)
from ..services.metrc_context import resolve_metrc_context
from ..services.metrc_transfer_actions import (
    GovernedMetrcTransferActionService,
    MetrcTransferActionError,
    PROMOTED_TRANSFER_ACTIONS,
    transfer_confirmation_token,
)

router = APIRouter(prefix="/inventory/transfers", tags=["inventory-transfers"])
TRANSFER_WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}
TransferOperation = Literal["transfer_template_create", "transfer_template_update"]


class TransferRegulatoryActionRequest(BaseModel):
    operation_type: TransferOperation
    payload: dict[str, Any]
    reason: str = Field(default="Controlled Metrc transfer-template action", min_length=3, max_length=255)


class TransferRegulatoryActionExecute(TransferRegulatoryActionRequest):
    confirmation_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=32, max_length=128)


def _require_inventory_scope(context: RequestContext, engine: Engine) -> None:
    require_any_facility_capability(context, engine, ("retail", "production", "cultivation"))


def _require_transfer_write(context: RequestContext) -> None:
    if context.role.casefold() not in TRANSFER_WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow cross-license inventory transfers.")


def _metrc_transfer_context(context: RequestContext, engine: Engine, settings: Settings):
    _require_inventory_scope(context, engine)
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    if metrc.status != "connected" or not metrc.trusted_mapping:
        raise HTTPException(
            409,
            "Validate the exact Metrc facility/license mapping before using governed transfer-template actions.",
        )
    if str(metrc.state or "").strip().upper() != "MA" or str(metrc.environment or "").strip().casefold() != "sandbox":
        raise HTTPException(
            409,
            "Promoted transfer-template writes are currently restricted to the verified Massachusetts Metrc sandbox.",
        )
    return metrc


@router.get("", response_model=list[InventoryTransferItem])
def list_inventory_transfers(
    direction: str = Query(default="both", pattern="^(inbound|outbound|both)$"),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_inventory_scope(context, engine)
    try:
        return InventoryTransferService(engine).list_for_facility(
            context.organization_id,
            context.facility_id,
            direction,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/regulatory-actions/status")
def transfer_regulatory_action_status(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_inventory_scope(context, engine)
    try:
        _, metrc = resolve_metrc_context(engine, settings, context)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    jurisdiction = str(metrc.state or "").strip().upper()
    environment = str(metrc.environment or "").strip().casefold()
    ready = bool(
        metrc.configured
        and metrc.status == "connected"
        and metrc.trusted_mapping
        and jurisdiction == "MA"
        and environment == "sandbox"
    )
    return {
        "ready": ready,
        "provider": "metrc",
        "jurisdiction_code": jurisdiction,
        "environment": environment,
        "license_number": str(metrc.license_number or "").strip(),
        "promoted_actions": sorted(PROMOTED_TRANSFER_ACTIONS) if ready else [],
        "documentation_source": "https://api-ma.metrc.com/Documentation",
        "execution_host": "sandbox-api-ma.metrc.com" if ready else "",
        "message": (
            "Current Massachusetts Metrc v2 outgoing transfer-template actions are available."
            if ready
            else str(metrc.message or "This facility remains on the existing state-system-confirmed transfer workflow.")
        ),
        "provider_boundary": (
            "The current MA v2 API exposes outgoing transfer-template writes. A verified template is not itself proof of an outgoing regulatory manifest."
        ),
    }


@router.post("/regulatory-actions/preview")
def preview_transfer_regulatory_action(
    payload: TransferRegulatoryActionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_transfer_write(context)
    metrc = _metrc_transfer_context(context, engine, settings)
    service = GovernedMetrcTransferActionService(engine)
    try:
        prepared = service.prepare(
            operation_type=payload.operation_type,
            payload=payload.payload,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
        )
        confirmation_id = str(uuid4())
        token = transfer_confirmation_token(
            prepared=prepared,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            confirmation_id=confirmation_id,
        )
        spec = TRANSFER_WRITE_EVALUATION_ACTIONS[prepared["operation_type"]]
        return {
            "ready": True,
            "operation_type": prepared["operation_type"],
            "summary": prepared["summary"],
            "confirmation_id": confirmation_id,
            "confirmation_token": token,
            "compliance_evidence": {
                "method": spec["method"],
                "path": spec["path"],
                "license_number": metrc.license_number,
                "environment": metrc.environment,
                "provider_request_body": prepared["provider_request_body"],
                "documentation_source": "https://api-ma.metrc.com/Documentation",
            },
            "message": "Review the transfer-template values before confirming. This does not claim the regulatory manifest has been created.",
        }
    except MetrcTransferActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/regulatory-actions/execute")
def execute_transfer_regulatory_action(
    payload: TransferRegulatoryActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _require_transfer_write(context)
    metrc = _metrc_transfer_context(context, engine, settings)
    try:
        return GovernedMetrcTransferActionService(engine).execute(
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
    except MetrcTransferActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{transfer_id}", response_model=InventoryTransferItem)
def inventory_transfer_detail(
    transfer_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_inventory_scope(context, engine)
    try:
        return InventoryTransferService(engine).detail(
            context.organization_id,
            transfer_id,
            facility_id=context.facility_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/dispatch", response_model=InventoryTransferItem, status_code=201)
def dispatch_inventory_transfer(
    payload: InventoryTransferDispatchCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_inventory_scope(context, engine)
    _require_transfer_write(context)
    if not payload.state_transfer_confirmed:
        raise HTTPException(
            422,
            "Confirm the required state-system/Metrc transfer and manifest before posting the physical transfer-out in DoobieLogic.",
        )
    try:
        return InventoryTransferService(engine).dispatch(
            context.organization_id,
            context.facility_id,
            destination_facility_id=payload.destination_facility_id,
            manifest_reference=payload.manifest_reference,
            external_transfer_id=payload.external_transfer_id,
            notes=payload.notes,
            lines=[row.model_dump() for row in payload.lines],
            actor=context.user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status = 409 if any(token in detail.casefold() for token in ("already exists", "exceeds available", "commitment")) else 422
        raise HTTPException(status, detail) from exc


@router.post("/{transfer_id}/lines/{line_id}/receive", response_model=InventoryTransferItem)
def receive_inventory_transfer_line(
    transfer_id: str,
    line_id: str,
    payload: InventoryTransferReceiveLine,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_transfer_write(context)
    require_inventory_operation_capability(context, engine, payload.operation)
    if not payload.state_receipt_confirmed:
        raise HTTPException(
            422,
            "Confirm the package was accepted/received in the required state system before posting destination inventory in DoobieLogic.",
        )
    try:
        MetrcTransferReadinessService(engine).assert_receivable(context.organization_id, transfer_id, line_id)
        return InventoryTransferService(engine).receive_line(
            context.organization_id,
            context.facility_id,
            transfer_id,
            line_id,
            operation=payload.operation,
            lot_code=payload.lot_code,
            package_id=payload.package_id,
            location=payload.location,
            notes=payload.notes,
            actor=context.user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(409 if "already" in detail.casefold() else 422, detail) from exc


@router.post("/{transfer_id}/cancel", response_model=InventoryTransferItem)
def cancel_inventory_transfer(
    transfer_id: str,
    payload: InventoryTransferCancel,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_inventory_scope(context, engine)
    _require_transfer_write(context)
    if not payload.state_cancel_confirmed:
        raise HTTPException(
            422,
            "Confirm the required state-system/Metrc transfer cancellation before restoring source inventory in DoobieLogic.",
        )
    try:
        MetrcTransferReadinessService(engine).assert_cancellable(context.organization_id, transfer_id)
        return InventoryTransferService(engine).cancel(
            context.organization_id,
            context.facility_id,
            transfer_id,
            actor=context.user_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
