from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import BomComponent, ProductBom
from modules.coman.repository import ComanRepository
from ..auth import RequestContext, get_production_context, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/coman-parity", tags=["coman-parity"], dependencies=[Depends(get_production_context)])


def _repo(engine: Engine) -> ComanRepository:
    return ComanRepository(engine)


def _value(row: Any, name: str, default: Any = None) -> Any:
    return getattr(row, name, default)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("/workspace")
def workspace(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    try:
        customers = repo.list_customers(context.organization_id)
        orders = repo.list_production_orders(context.organization_id, context.facility_id)
        machine_models = repo.list_machine_models()
        machines = repo.list_facility_machines(context.organization_id, context.facility_id)
        hand = repo.ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
        actuals = repo.list_production_actuals(context.organization_id, context.facility_id)
        crew = repo.list_crew_availability(context.organization_id, context.facility_id)
        products = repo.list_products(context.organization_id)
        lots = repo.list_inventory_lots(context.organization_id, context.facility_id)
        transactions = repo.list_inventory_transactions(context.organization_id, context.facility_id, limit=250)
        reservations = repo.list_material_reservations(context.organization_id, context.facility_id)
        with Session(engine) as session:
            boms = list(session.scalars(select(ProductBom).where(ProductBom.organization_id == context.organization_id).order_by(ProductBom.created_at.desc())))
            bom_ids = [row.id for row in boms]
            components = list(session.scalars(select(BomComponent).where(BomComponent.bom_id.in_(bom_ids)))) if bom_ids else []
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc

    customers_by_id = {str(row.id): row for row in customers}
    products_by_id = {str(row.id): row for row in products}
    models_by_id = {str(row.id): row for row in machine_models}
    components_by_bom: dict[str, list[Any]] = {}
    for component in components:
        components_by_bom.setdefault(str(component.bom_id), []).append(component)
    open_orders = [row for row in orders if str(row.status) not in {"complete", "cancelled"}]
    return {
        "summary": {
            "open_orders": len(open_orders),
            "units_planned": sum(int(_value(row, "requested_units", 0) or 0) for row in open_orders),
            "external_jobs": sum(str(_value(row, "work_type", "")) == "external" for row in orders),
            "customers": len(customers),
        },
        "readiness": [
            {"requirement": "Facility selected", "status": "Ready"},
            {"requirement": "Hand-labor rates", "status": "Ready" if all(float(_value(hand, key, 0) or 0) > 0 for key in ("sticker_units_per_person_hour", "case_pack_units_per_person_hour", "final_cases_per_person_hour")) else "Needs setup"},
            {"requirement": "Facility machine", "status": "Ready" if machines else "Needs setup"},
            {"requirement": "Production queue", "status": "Ready" if orders else "No jobs yet"},
        ],
        "orders": [{
            "id": str(row.id), "order_number": row.order_number, "work_type": row.work_type,
            "customer": _value(customers_by_id.get(str(_value(row, "customer_id", ""))), "name", "Internal"),
            "customer_id": _value(row, "customer_id", None), "product_name": row.product_name, "product_format": row.product_format,
            "requested_units": row.requested_units, "due_at": _iso(_value(row, "due_at")), "priority": row.priority,
            "status": row.status, "source_lot_reference": _value(row, "source_lot_reference", ""), "sku": _value(row, "sku", ""),
            "material_owner": _value(row, "material_owner", "internal"), "packaging_owner": _value(row, "packaging_owner", "internal"), "notes": _value(row, "notes", ""),
        } for row in orders],
        "customers": [{"id": str(row.id), "name": row.name, "license_or_registration": _value(row, "license_or_registration", ""), "contact_name": _value(row, "contact_name", ""), "contact_email": _value(row, "contact_email", "")} for row in customers],
        "machine_models": [{"id": str(row.id), "manufacturer": row.manufacturer, "model": row.model, "category": row.category, "published_max_rate": float(_value(row, "published_max_rate", 0) or 0), "rate_unit": _value(row, "rate_unit", "units/hour"), "planning_utilization_pct": float(_value(row, "planning_utilization_pct", 0) or 0), "published_min_operators": int(_value(row, "published_min_operators", 0) or 0), "source_url": _value(row, "source_url", "")} for row in machine_models],
        "machines": [{"id": str(row.id), "asset_code": row.asset_code, "display_name": row.display_name, "machine_model": _value(models_by_id.get(str(row.machine_model_id)), "model", "Unknown"), "machine_model_id": str(row.machine_model_id), "effective_rate": float(row.effective_rate), "rate_unit": row.rate_unit, "preferred_crew_size": int(row.preferred_crew_size), "setup_minutes": int(row.setup_minutes), "cleanup_minutes": int(row.cleanup_minutes)} for row in machines],
        "hand_labor": {"id": str(hand.id), "default_crew_size": int(hand.default_crew_size), "sticker_units_per_person_hour": float(hand.sticker_units_per_person_hour), "case_pack_units_per_person_hour": float(hand.case_pack_units_per_person_hour), "final_cases_per_person_hour": float(hand.final_cases_per_person_hour), "setup_minutes": int(hand.setup_minutes), "cleanup_minutes": int(hand.cleanup_minutes)},
        "crew": [{"id": str(row.id), "work_date": _iso(row.work_date), "shift_name": row.shift_name, "available_people": int(row.available_people), "shift_hours": float(row.shift_hours), "notes": _value(row, "notes", "")} for row in crew],
        "products": [{"id": str(row.id), "sku": row.sku, "name": row.name, "item_type": row.item_type, "base_unit": row.base_unit, "unit_cost": float(_value(row, "unit_cost", 0) or 0)} for row in products],
        "lots": [{"id": str(row.id), "product_id": str(row.product_id), "product_name": _value(products_by_id.get(str(row.product_id)), "name", "Unknown"), "lot_code": row.lot_code, "location_code": row.location_code, "compliance_package_id": _value(row, "compliance_package_id", ""), "status": _value(row, "status", "available"), "received_at": _iso(_value(row, "received_at")), "balance": repo.inventory_balance(context.organization_id, str(row.id))} for row in lots],
        "transactions": [{"id": str(row.id), "lot_id": str(row.lot_id), "transaction_type": row.transaction_type, "quantity_delta": float(row.quantity_delta), "unit": row.unit, "reason": _value(row, "reason", ""), "reference": _value(row, "reference", ""), "actor": _value(row, "actor", ""), "occurred_at": _iso(_value(row, "occurred_at"))} for row in transactions],
        "reservations": [{"id": str(row.id), "production_order_id": str(row.production_order_id), "lot_id": str(row.lot_id), "quantity": float(row.quantity), "unit": row.unit, "status": row.status} for row in reservations],
        "boms": [{"id": str(row.id), "output_product_id": str(row.output_product_id), "output_product_name": _value(products_by_id.get(str(row.output_product_id)), "name", "Unknown"), "version": int(row.version), "output_quantity": float(row.output_quantity), "expected_loss_pct": float(row.expected_loss_pct), "notes": _value(row, "notes", ""), "components": [{"id": str(component.id), "input_product_id": str(component.input_product_id), "input_product_name": _value(products_by_id.get(str(component.input_product_id)), "name", "Unknown"), "quantity": float(component.quantity), "unit": component.unit, "scrap_pct": float(component.scrap_pct)} for component in components_by_bom.get(str(row.id), [])]} for row in boms],
        "actuals": [{"id": str(row.id), "production_order_id": str(row.production_order_id), "actual_units": int(row.actual_units), "scrap_units": int(row.scrap_units), "rework_units": int(row.rework_units), "actual_machine_hours": float(row.actual_machine_hours), "actual_labor_hours": float(row.actual_labor_hours), "completed_at": _iso(row.completed_at), "notes": _value(row, "notes", "")} for row in actuals],
    }


class OrderCreate(BaseModel):
    order_number: str
    work_type: str = "internal"
    product_name: str
    product_format: str
    requested_units: int = Field(gt=0)
    customer_id: str | None = None
    due_at: datetime | None = None
    sku: str = ""
    priority: str = "normal"
    source_lot_reference: str = ""
    material_owner: str = "internal"
    packaging_owner: str = "internal"
    notes: str = ""


@router.post("/orders", status_code=201)
def create_order(payload: OrderCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_production_order(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id), "order_number": row.order_number}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class StatusUpdate(BaseModel):
    status: str


@router.post("/orders/{order_id}/status")
def update_order_status(order_id: str, payload: StatusUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).update_production_order_status(order_id, organization_id=context.organization_id, facility_id=context.facility_id, status=payload.status, actor=context.user_id)
        return {"id": str(row.id), "status": row.status}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class DuplicateCreate(BaseModel):
    order_number: str


@router.post("/orders/{order_id}/duplicate", status_code=201)
def duplicate_order(order_id: str, payload: DuplicateCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).duplicate_production_order(order_id, organization_id=context.organization_id, facility_id=context.facility_id, new_order_number=payload.order_number, actor=context.user_id)
        return {"id": str(row.id), "order_number": row.order_number}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class CustomerCreate(BaseModel):
    name: str
    license_or_registration: str = ""
    contact_name: str = ""
    contact_email: str = ""


@router.post("/customers", status_code=201)
def create_customer(payload: CustomerCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_customer(context.organization_id, payload.name, license_or_registration=payload.license_or_registration, contact_name=payload.contact_name, contact_email=payload.contact_email)
        return {"id": str(row.id), "name": row.name}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class ProductCreate(BaseModel):
    sku: str
    name: str
    item_type: str = "cannabis"
    base_unit: str = "g"
    unit_cost: float = Field(ge=0, default=0)


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_product(context.organization_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id), "sku": row.sku, "name": row.name}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class MachineCreate(BaseModel):
    machine_model_id: str
    asset_code: str
    display_name: str
    effective_rate: float = Field(gt=0)
    preferred_crew_size: int = Field(ge=1)
    setup_minutes: int = Field(ge=0, default=30)
    cleanup_minutes: int = Field(ge=0, default=30)


@router.post("/machines", status_code=201)
def create_machine(payload: MachineCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_facility_machine(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id), "display_name": row.display_name}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class HandLaborUpdate(BaseModel):
    default_crew_size: int = Field(ge=1)
    sticker_units_per_person_hour: float = Field(ge=0)
    case_pack_units_per_person_hour: float = Field(ge=0)
    final_cases_per_person_hour: float = Field(ge=0)
    setup_minutes: int = Field(ge=0)
    cleanup_minutes: int = Field(ge=0)


@router.post("/hand-labor")
def update_hand_labor(payload: HandLaborUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    try:
        current = repo.ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
        row = repo.update_hand_labor_area(current.id, organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class LotCreate(BaseModel):
    product_id: str
    lot_code: str
    opening_quantity: float = Field(ge=0)
    location_code: str = "RECEIVING"
    compliance_package_id: str = ""
    unit: str | None = None


@router.post("/lots", status_code=201)
def create_lot(payload: LotCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_inventory_lot(context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id), "lot_code": row.lot_code}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class InventoryTransactionCreate(BaseModel):
    lot_id: str
    transaction_type: str
    quantity_delta: float
    unit: str
    production_order_id: str | None = None
    reason: str = ""
    reference: str = ""


@router.post("/transactions", status_code=201)
def post_transaction(payload: InventoryTransactionCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).post_inventory_transaction(context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class ReservationCreate(BaseModel):
    production_order_id: str
    lot_id: str
    quantity: float = Field(gt=0)
    unit: str


@router.post("/reservations", status_code=201)
def create_reservation(payload: ReservationCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).reserve_material(context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class BomComponentCreate(BaseModel):
    input_product_id: str
    quantity: float = Field(gt=0)
    unit: str
    scrap_pct: float = Field(ge=0, default=0)


class BomCreate(BaseModel):
    output_product_id: str
    output_quantity: float = Field(gt=0)
    expected_loss_pct: float = Field(ge=0, default=0)
    notes: str = ""
    components: list[BomComponentCreate]


@router.post("/boms", status_code=201)
def create_bom(payload: BomCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        body = payload.model_dump()
        row = _repo(engine).create_bom(context.organization_id, actor=context.user_id, **body)
        return {"id": str(row.id), "version": int(row.version)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


class ActualCreate(BaseModel):
    actual_units: int = Field(ge=0)
    scrap_units: int = Field(ge=0, default=0)
    rework_units: int = Field(ge=0, default=0)
    actual_machine_hours: float = Field(ge=0, default=0)
    actual_labor_hours: float = Field(ge=0, default=0)
    notes: str = ""


@router.post("/orders/{order_id}/actuals", status_code=201)
def record_actual(order_id: str, payload: ActualCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).record_production_actual(order_id, organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": str(row.id)}
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
