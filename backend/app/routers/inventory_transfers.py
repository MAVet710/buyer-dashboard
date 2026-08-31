from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from modules.inventory_transfers.commercial_handoff import CommercialTransferHandoffService
from modules.inventory_transfers.service import InventoryTransferService
from ..auth import RequestContext, get_request_context, require_any_facility_capability, require_inventory_operation_capability
from ..database import get_engine
from ..schemas.inventory_transfers import (
    InventoryTransferCancel,
    InventoryTransferDispatchCreate,
    InventoryTransferItem,
    InventoryTransferReceiveLine,
)

router = APIRouter(prefix="/inventory/transfers", tags=["inventory-transfers"])
TRANSFER_WRITE_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


def _require_inventory_scope(context: RequestContext, engine: Engine) -> None:
    require_any_facility_capability(context, engine, ("retail", "production", "cultivation"))


def _require_transfer_write(context: RequestContext) -> None:
    if context.role.casefold() not in TRANSFER_WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow cross-license inventory transfers.")


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
    commercial_lines = [row for row in payload.lines if row.commercial_order_line_id]
    if commercial_lines and len(commercial_lines) != len(payload.lines):
        raise HTTPException(422, "Do not mix reserved wholesale fulfillment and ordinary inventory packages on the same transfer.")
    try:
        service = CommercialTransferHandoffService(engine) if commercial_lines else InventoryTransferService(engine)
        return service.dispatch(
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
        status = 409 if any(token in detail.casefold() for token in ("already exists", "exceeds", "commitment", "reserved", "no longer")) else 422
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
        commercial = CommercialTransferHandoffService(engine)
        if commercial.is_commercial_handoff(context.organization_id, context.facility_id, transfer_id):
            return commercial.cancel(
                context.organization_id,
                context.facility_id,
                transfer_id,
                actor=context.user_id,
                reason=payload.reason,
            )
        return InventoryTransferService(engine).cancel(
            context.organization_id,
            context.facility_id,
            transfer_id,
            actor=context.user_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc