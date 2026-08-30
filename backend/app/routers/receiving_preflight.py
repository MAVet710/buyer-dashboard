from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.traceability.models import ReceivingPreflight
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..schemas.inventory import InventoryReceiptCreate
from ..services.receiving_preflight import ReceivingPreflightService
from .inventory import _metrc_context


router = APIRouter(tags=["inventory"])
DISCREPANCY_RESOLUTION_ROLES = {"dev", "admin", "supervisor", "qa"}


class ReceivingObservation(BaseModel):
    package_id: str = Field(min_length=1, max_length=255)
    observed_quantity: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=64)
    condition: Literal["ok", "damaged", "other"] = "ok"
    note: str = Field(default="", max_length=2000)


class ReceivingPreflightCommit(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=64)
    receipts: list[InventoryReceiptCreate] = Field(min_length=1, max_length=500)
    observations: list[ReceivingObservation] = Field(default_factory=list, max_length=500)


class ReceivingDiscrepancyRecord(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=64)
    observations: list[ReceivingObservation] = Field(min_length=1, max_length=500)


class ReceivingDiscrepancyResolution(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=2000)


def _can_resolve(context: RequestContext) -> bool:
    return context.role.casefold() in DISCREPANCY_RESOLUTION_ROLES


def _require_preflight_transfer(
    *,
    engine: Engine,
    context: RequestContext,
    operation: str,
    transfer_id: str,
    preflight_id: str,
) -> None:
    """Fail closed when a preflight is not bound to this exact facility/transfer."""
    with Session(engine) as session:
        row = session.scalar(
            select(ReceivingPreflight).where(
                ReceivingPreflight.id == preflight_id,
                ReceivingPreflight.organization_id == context.organization_id,
                ReceivingPreflight.facility_id == context.facility_id,
                ReceivingPreflight.operation == operation,
                ReceivingPreflight.transfer_id == str(transfer_id or "").strip(),
            )
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Receiving preflight was not found for this inbound transfer and active facility.")


@router.post("/{operation}/inbound/{transfer_id}/preflight", status_code=201)
def prepare_receiving_preflight(
    operation: str,
    transfer_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Record an exact, read-only provider snapshot before local receiving.

    This endpoint does not accept the transfer in Metrc and performs no provider
    mutation. It proves that the transfer is still pending under the exact
    verified facility mapping and records all remaining provider packages.
    """

    metrc = _metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    if not metrc.configured:
        raise HTTPException(status_code=422, detail=metrc.message)
    try:
        return ReceivingPreflightService(engine).prepare(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            actor=context.user_id,
            transfer_id=transfer_id,
            metrc=metrc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{operation}/inbound/{transfer_id}/preflight/{preflight_id}/discrepancies")
def receiving_discrepancies(
    operation: str,
    transfer_id: str,
    preflight_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_preflight_transfer(engine=engine, context=context, operation=operation, transfer_id=transfer_id, preflight_id=preflight_id)
    service = ReceivingPreflightService(engine)
    try:
        rows = service.list_discrepancies(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            preflight_id=preflight_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "preflight_id": preflight_id,
        "transfer_id": transfer_id,
        "can_resolve": _can_resolve(context),
        "open_count": sum(1 for row in rows if row.get("status") == "open"),
        "discrepancies": rows,
    }


@router.post("/{operation}/inbound/{transfer_id}/preflight/discrepancies")
def record_receiving_discrepancies(
    operation: str,
    transfer_id: str,
    payload: ReceivingDiscrepancyRecord,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_preflight_transfer(engine=engine, context=context, operation=operation, transfer_id=transfer_id, preflight_id=payload.preflight_id)
    try:
        result = ReceivingPreflightService(engine).record_observations(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            actor=context.user_id,
            preflight_id=payload.preflight_id,
            transfer_id=transfer_id,
            observations=[row.model_dump() for row in payload.observations],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result["can_resolve"] = _can_resolve(context)
    return result


@router.post("/{operation}/inbound/{transfer_id}/preflight/{preflight_id}/discrepancies/{discrepancy_id}/resolve")
def resolve_receiving_discrepancy(
    operation: str,
    transfer_id: str,
    preflight_id: str,
    discrepancy_id: str,
    payload: ReceivingDiscrepancyResolution,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if not _can_resolve(context):
        raise HTTPException(status_code=403, detail="Only an authorized supervisor, QA, admin, or developer can resolve receiving discrepancies.")
    _require_preflight_transfer(engine=engine, context=context, operation=operation, transfer_id=transfer_id, preflight_id=preflight_id)
    service = ReceivingPreflightService(engine)
    try:
        rows = service.list_discrepancies(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            preflight_id=preflight_id,
        )
        target = next((row for row in rows if row["id"] == discrepancy_id), None)
        if target is None:
            raise ValueError("Receiving discrepancy was not found for this inbound transfer.")
        return service.resolve_discrepancy(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            actor=context.user_id,
            preflight_id=preflight_id,
            discrepancy_id=discrepancy_id,
            resolution_note=payload.resolution_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{operation}/inbound/{transfer_id}/preflight/commit")
def commit_receiving_preflight(
    operation: str,
    transfer_id: str,
    payload: ReceivingPreflightCommit,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Fresh-read Metrc and post the reviewed local receipt atomically.

    If physical observations are supplied, their package set/count/unit/condition
    must exactly match the prepared provider snapshot. Any previously recorded
    physical discrepancy must be resolved. After any discrepancy history exists,
    an exact fresh physical observation set is mandatory before posting. A
    second provider read must also exactly match the prepared snapshot. No Metrc
    write is issued here.
    """

    _require_preflight_transfer(engine=engine, context=context, operation=operation, transfer_id=transfer_id, preflight_id=payload.preflight_id)
    service = ReceivingPreflightService(engine)
    try:
        discrepancy_history = service.list_discrepancies(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            preflight_id=payload.preflight_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if discrepancy_history and not payload.observations:
        raise HTTPException(status_code=409, detail="A fresh exact physical count is required after a receiving discrepancy before local inventory can be posted.")

    metrc = _metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    if not metrc.configured:
        raise HTTPException(status_code=422, detail=metrc.message)
    try:
        return service.commit(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            actor=context.user_id,
            preflight_id=payload.preflight_id,
            transfer_id=transfer_id,
            rows=payload.receipts,
            observations=[row.model_dump() for row in payload.observations],
            metrc=metrc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
