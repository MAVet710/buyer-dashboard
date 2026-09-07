"""Authenticated buyer comparison and PO-proposal endpoints for supplier offers."""

from __future__ import annotations

from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.supplier_portal.buying import SupplierBuyingService

from ..auth import RequestContext, get_request_context
from ..database import get_engine


router = APIRouter(prefix="/supplier-portal", tags=["supplier-buying"])
BUYER_ROLES = {"dev", "admin", "buyer"}


def _require_buyer(context: RequestContext) -> None:
    if context.role.casefold() not in BUYER_ROLES:
        raise HTTPException(403, "Your role does not allow supplier offer comparison or purchase-order proposals.")


class SupplierLineSelection(BaseModel):
    line_id: str = Field(min_length=1, max_length=36)
    quantity: float = Field(gt=0)


class SupplierPurchaseOrderProposal(BaseModel):
    selections: list[SupplierLineSelection] = Field(min_length=1, max_length=500)
    due_date: date | None = None
    order_number: str = Field(default="", max_length=80)
    stale_after_days: int = Field(default=14, ge=1, le=90)


def _proposal_payload(row):
    return {
        "id": row.id,
        "action_type": row.action_type,
        "title": row.title,
        "rationale": row.rationale,
        "financial_impact_usd": row.financial_impact_usd,
        "risk_level": row.risk_level,
        "status": row.status,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "payload": json.loads(row.payload_json or "{}"),
        "preview": json.loads(row.preview_json or "{}"),
    }


@router.get("/offers/{offer_id}/comparison")
def compare_supplier_offer(
    offer_id: str,
    lookback_days: int = Query(default=60, ge=14, le=120),
    stale_after_days: int = Query(default=14, ge=1, le=90),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_buyer(context)
    try:
        return SupplierBuyingService(engine).compare_offer(
            context.organization_id,
            context.facility_id,
            offer_id,
            lookback_days=lookback_days,
            stale_after_days=stale_after_days,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/offers/{offer_id}/purchase-order-proposal", status_code=201)
def create_supplier_purchase_order_proposal(
    offer_id: str,
    payload: SupplierPurchaseOrderProposal,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_buyer(context)
    try:
        proposal = SupplierBuyingService(engine).propose_purchase_order(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            offer_id=offer_id,
            selections=[row.model_dump() for row in payload.selections],
            actor=context.user_id,
            due_date=payload.due_date,
            order_number=payload.order_number,
            stale_after_days=payload.stale_after_days,
        )
        return _proposal_payload(proposal)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
