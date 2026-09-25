"""Scoped planning documents and governed canonical execution handoffs."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, Product
from modules.repack.execution import WhiteLabelService
from ..auth import RequestContext, get_request_context, require_any_facility_capability, require_facility_capability
from ..database import get_engine
from ..permissions import require_permission

router = APIRouter(prefix="/white-label", tags=["white-label"])
EDIT_ROLES = {"dev", "admin", "buyer", "planner", "supervisor"}


class Allocation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    enabled: bool
    package_size_g: float = Field(ge=0, le=1000000)
    allocation_pct: float = Field(ge=0, le=100)
    bag_or_container_cost_per_unit: float = Field(default=0, ge=0)
    label_cost_per_unit: float = Field(default=0, ge=0)
    tamper_seal_cost_per_unit: float = Field(default=0, ge=0)
    humidity_pack_cost_per_unit: float = Field(default=0, ge=0)
    compliance_sticker_cost_per_unit: float = Field(default=0, ge=0)
    other_packaging_cost_per_unit: float = Field(default=0, ge=0)
    target_retail_price_per_unit: float = Field(default=0, ge=0)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    form: dict[str, str | float]
    plan: list[Allocation] = Field(min_length=1, max_length=100)
    simpleMode: bool = True

    @field_validator("form")
    @classmethod
    def bounded_form(cls, value):
        if len(value) > 80 or any(len(k) > 100 or (isinstance(v, str) and len(v) > 4000) for k, v in value.items()):
            raise ValueError("Plan form exceeds supported size.")
        return value


class PlanSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    source_lot_id: str = Field(min_length=1, max_length=36)
    scenario: Scenario
    revision: int | None = Field(default=None, ge=1)


class Revision(BaseModel):
    revision: int = Field(ge=1)


def _scope(context, engine, write=False, approve=False):
    require_any_facility_capability(context, engine, ("retail", "production"))
    if write and context.role.casefold() not in EDIT_ROLES:
        raise HTTPException(403, "Your role cannot change White Label plans.")
    if write:
        require_permission(context, engine, "white_label.manage_plans")
    if approve:
        require_facility_capability(context, engine, "production")


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, OverflowError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/sources")
def sources(q: str = Query(default="", max_length=120), offset: int = Query(default=0, ge=0),
            context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _scope(context, engine)
    with Session(engine) as session:
        rows = session.execute(select(InventoryLot.id, InventoryLot.lot_code,
            InventoryLot.compliance_package_id.label("package_id"), Product.name.label("product_name"), InventoryLot.status
        ).join(Product, Product.id == InventoryLot.product_id).where(
            InventoryLot.organization_id == context.organization_id, InventoryLot.facility_id == context.facility_id,
            Product.organization_id == context.organization_id, Product.base_unit.in_(("g", "kg", "oz", "lb")),
            or_(InventoryLot.lot_code.ilike(f"%{q}%"), InventoryLot.compliance_package_id.ilike(f"%{q}%"), Product.name.ilike(f"%{q}%"))
        ).order_by(InventoryLot.lot_code, InventoryLot.id).offset(offset).limit(100)).all()
        return [dict(row._mapping) for row in rows]


@router.get("/plans")
def plans(offset: int = Query(default=0, ge=0), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _scope(context, engine)
    return WhiteLabelService(engine).list(context.organization_id, context.facility_id, offset)


@router.get("/plans/{plan_id}")
def plan(plan_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _scope(context, engine)
    return _call(WhiteLabelService(engine).get, context.organization_id, context.facility_id, plan_id)


@router.post("/plans")
def create(payload: PlanSave, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return save(None, payload, context, engine)


@router.post("/plans/{plan_id}")
def save(plan_id: str, payload: PlanSave, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _scope(context, engine, write=True)
    return _call(WhiteLabelService(engine).save, context.organization_id, context.facility_id, context.user_id, payload.model_dump(), plan_id)


@router.post("/plans/{plan_id}/approve")
def approve(plan_id: str, payload: Revision, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _scope(context, engine, write=True, approve=True)
    return _call(WhiteLabelService(engine).approve, context.organization_id, context.facility_id, context.user_id, plan_id, payload.revision)


@router.post("/plans/{plan_id}/cancel")
def cancel(plan_id: str, payload: Revision, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _scope(context, engine, write=True)
    return _call(WhiteLabelService(engine).cancel, context.organization_id, context.facility_id, context.user_id, plan_id, payload.revision)
