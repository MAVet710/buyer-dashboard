from __future__ import annotations

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


class ReceivingPreflightCommit(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=64)
    receipts: list[InventoryReceiptCreate] = Field(min_length=1, max_length=500)


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


@router.post("/{operation}/inbound/{transfer_id}/preflight/commit")
def commit_receiving_preflight(
    operation: str,
    transfer_id: str,
    payload: ReceivingPreflightCommit,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    """Fresh-read Metrc and post the matching local receipt atomically.

    A second provider read must exactly match the prepared package snapshot.
    Provider package identity, remaining quantity, unit, manifest/source and lab
    state are authoritative. Product mapping, room and operator notes remain the
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
            metrc=metrc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
