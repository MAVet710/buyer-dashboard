from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

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
    observations: list[ReceivingObservation] = Field(min_length=1, max_length=500)


class ReceivingDiscrepancyRecord(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=64)
    observations: list[ReceivingObservation] = Field(min_length=1, max_length=500)


class ReceivingDiscrepancyResolution(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=2000)


def _can_resolve(context: RequestContext) -> bool:
    return context.role.casefold() in DISCREPANCY_RESOLUTION_ROLES


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
    if rows and any(str(row.get("transfer_id") or "") != str(transfer_id) for row in rows):
        raise HTTPException(status_code=404, detail="Receiving discrepancy was not found for this inbound transfer.")
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
    try:
        rows = ReceivingPreflightService(engine).list_discrepancies(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            operation=operation,
            preflight_id=preflight_id,
        )
        target = next((row for row in rows if row["id"] == discrepancy_id), None)
        if target is None or str(target.get("transfer_id") or "") != str(transfer_id):
            raise ValueError("Receiving discrepancy was not found for this inbound transfer.")
        return ReceivingPreflightService(engine).resolve_discrepancy(
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
    """Fresh-read Metrc and post the physically matching local receipt atomically.

    The physical package set/count/unit must exactly match the prepared provider
    snapshot and there must be no unresolved receiving discrepancy. A second
    provider read must also exactly match the prepared snapshot. Provider
    package identity, remaining quantity, unit, manifest/source and lab state
    remain authoritative. Product mapping, room and operator notes remain the
    reviewed local fields. No Metrc write is issued by this endpoint.
    """

    metrc = _metrc_context(context=context, engine=engine, settings=settings, operation=operation)
    if not metrc.configured:
        raise HTTPException(status_code=422, detail=metrc.message)
    try:
        return ReceivingPreflightService(engine).commit(
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
