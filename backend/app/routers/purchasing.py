from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.commercial.repository import CommercialRepository
from modules.retail_planning import RetailPlanningService
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine

router = APIRouter(prefix="/purchasing", tags=["purchasing"], dependencies=[Depends(get_retail_context)])
BUY_ROLES = {"dev", "admin", "supervisor", "buyer"}


class PolicyUpdate(BaseModel):
    preferred_vendor_id: str | None = None
    target_doh: float = Field(default=30, ge=0)
    safety_stock: float = Field(default=0, ge=0)
    reorder_point: float = Field(default=0, ge=0)
    minimum_order_quantity: float = Field(default=0, ge=0)
    case_pack: float = Field(default=0, ge=0)
    velocity_window_days: int = Field(default=30, ge=7, le=180)
    active: bool = True


class PurchaseOrderLine(BaseModel):
    product_id: str
    quantity: float = Field(gt=0)
    unit: str
    unit_price: float = Field(default=0, ge=0)
    description: str = ""


class PurchaseOrderCreate(BaseModel):
    vendor_id: str
    order_number: str = Field(min_length=1, max_length=64)
    order_date: date = Field(default_factory=date.today)
    due_date: date | None = None
    notes: str = ""
    lines: list[PurchaseOrderLine] = Field(min_length=1, max_length=500)


def _require_buyer(context: RequestContext):
    if context.role.casefold() not in BUY_ROLES: raise HTTPException(403, "Your role does not allow purchasing changes.")


@router.get("/workspace")
def workspace(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return RetailPlanningService(engine).workspace(context.organization_id, context.facility_id)


@router.post("/policies/{product_id}")
def save_policy(product_id: str, payload: PolicyUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_buyer(context)
    try:
        row = RetailPlanningService(engine).upsert_policy(context.organization_id, context.facility_id, product_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "product_id", "preferred_vendor_id", "target_doh", "safety_stock", "reorder_point", "minimum_order_quantity", "case_pack", "velocity_window_days", "active")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/purchase-orders", status_code=201)
def create_purchase_order(payload: PurchaseOrderCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_buyer(context)
    try:
        row = CommercialRepository(engine).create_order(organization_id=context.organization_id, facility_id=context.facility_id, partner_id=payload.vendor_id, order_number=payload.order_number, order_type="purchase", order_date=payload.order_date, due_date=payload.due_date, lines=[line.model_dump() for line in payload.lines], actor=context.user_id, notes=payload.notes)
        return {"id": row.id, "order_number": row.order_number, "status": row.status}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
