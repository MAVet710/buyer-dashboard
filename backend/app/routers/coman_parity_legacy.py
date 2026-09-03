from datetime import date, datetime, time

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization
from modules.coman.order_prefill import build_recommended_order_prefill
from modules.coman.planning import (
    estimate_hand_labor_job,
    estimate_machine_job,
    recommend_weight_allocation,
    weight_to_grams,
)
from modules.coman.repository import ComanRepository
from reports.coman_report import _build_coman_executive_report_pdf
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine


router = APIRouter(prefix="/coman-parity", tags=["coman-parity"], dependencies=[Depends(get_production_context)])


def _repo(engine: Engine) -> ComanRepository:
    return ComanRepository(engine)


def _order(row) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "order_number": row.order_number,
        "work_type": row.work_type,
        "product_name": row.product_name,
        "product_format": row.product_format,
        "requested_units": row.requested_units,
        "due_at": row.due_at,
        "sku": row.sku,
        "priority": row.priority,
        "status": row.status,
        "source_lot_reference": row.source_lot_reference,
        "material_owner": row.material_owner,
        "packaging_owner": row.packaging_owner,
        "notes": row.notes,
    }


@router.get("/workspace")
def workspace(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    repo = _repo(engine)
    customers = repo.list_customers(context.organization_id)
    orders = repo.list_production_orders(context.organization_id, context.facility_id)
    machine_models = repo.list_machine_models()
    machines = repo.list_facility_machines(context.organization_id, context.facility_id)
    hand = repo.ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
    actuals = repo.list_production_actuals(context.organization_id, context.facility_id)
    crew = repo.list_crew_availability(context.organization_id, context.facility_id, date.today())
    products = repo.list_products(context.organization_id)
    lots = repo.list_inventory_lots(context.organization_id, context.facility_id)
    transactions = repo.list_inventory_transactions(context.organization_id, context.facility_id)
    reservations = repo.list_material_reservations(context.organization_id, context.facility_id)
    open_orders = [row for row in orders if row.status not in {"complete", "cancelled"}]
    return {
        "metrics": {
            "open_orders": len(open_orders),
            "units_planned": sum(row.requested_units for row in open_orders),
            "external_jobs": sum(row.work_type == "external" for row in orders),
            "customers": len(customers),
        },
        "readiness": [
            {"Requirement": "Facility selected", "Status": "Ready"},
            {"Requirement": "Hand-labor rates", "Status": "Ready" if all((hand.sticker_units_per_person_hour > 0, hand.case_pack_units_per_person_hour > 0, hand.final_cases_per_person_hour > 0)) else "Needs setup"},
            {"Requirement": "Facility machine", "Status": "Ready" if machines else "Needs setup"},
            {"Requirement": "Production queue", "Status": "Ready" if orders else "No jobs yet"},
        ],
        "orders": [_order(row) for row in orders],
        "customers": [
            {"id": row.id, "name": row.name, "license_or_registration": row.license_or_registration, "contact_name": row.contact_name, "contact_email": row.contact_email}
            for row in customers
        ],
        "machine_models": [
            {"id": row.id, "manufacturer": row.manufacturer, "model": row.model, "category": row.category, "published_max_rate": row.published_max_rate, "rate_unit": row.rate_unit, "planning_utilization_pct": row.planning_utilization_pct, "published_min_operators": row.published_min_operators, "source_url": row.source_url}
            for row in machine_models
        ],
        "machines": [
            {"id": row.id, "machine_model_id": row.machine_model_id, "asset_code": row.asset_code, "display_name": row.display_name, "effective_rate": row.effective_rate, "rate_unit": row.rate_unit, "preferred_crew_size": row.preferred_crew_size, "setup_minutes": row.setup_minutes, "cleanup_minutes": row.cleanup_minutes}
            for row in machines
        ],
        "hand_labor": {
            "id": hand.id,
            "default_crew_size": hand.default_crew_size,
            "sticker_units_per_person_hour": hand.sticker_units_per_person_hour,
            "case_pack_units_per_person_hour": hand.case_pack_units_per_person_hour,
            "final_cases_per_person_hour": hand.final_cases_per_person_hour,
            "setup_minutes": hand.setup_minutes,
            "cleanup_minutes": hand.cleanup_minutes,
        },
        "products": [
            {"id": row.id, "sku": row.sku, "name": row.name, "item_type": row.item_type, "base_unit": row.base_unit, "unit_cost": row.unit_cost}
            for row in products
        ],
        "lots": [
            {"id": row.id, "product_id": row.product_id, "lot_code": row.lot_code, "compliance_package_id": row.compliance_package_id, "location_code": row.location_code, "status": row.status, "on_hand": repo.inventory_balance(context.organization_id, row.id)}
            for row in lots
        ],
        "transactions": [
            {"id": row.id, "occurred_at": row.occurred_at, "lot_id": row.lot_id, "transaction_type": row.transaction_type, "quantity_delta": row.quantity_delta, "unit": row.unit, "reason": row.reason, "reference": row.reference, "actor": row.actor}
            for row in transactions
        ],
        "reservations": [
            {"id": row.id, "production_order_id": row.production_order_id, "lot_id": row.lot_id, "quantity": row.quantity, "unit": row.unit, "status": row.status}
            for row in reservations
        ],
        "crew": [
            {"id": row.id, "work_date": row.work_date, "shift_name": row.shift_name, "available_people": row.available_people, "shift_hours": row.shift_hours, "notes": row.notes}
            for row in crew
        ],
        "actuals": [
            {"id": row.id, "production_order_id": row.production_order_id, "actual_units": row.actual_units, "scrap_units": row.scrap_units, "rework_units": row.rework_units, "actual_machine_hours": row.actual_machine_hours, "actual_labor_hours": row.actual_labor_hours, "completed_at": row.completed_at, "notes": row.notes}
            for row in actuals
        ],
    }


class StatusRequest(BaseModel):
    status: str


@router.post("/orders/{order_id}/status")
def update_status(
    order_id: str,
    payload: StatusRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        row = _repo(engine).update_production_order_status(
            order_id,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            status=payload.status,
            actor=context.user_id,
        )
        return _order(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class DuplicateRequest(BaseModel):
    new_order_number: str


@router.post("/orders/{order_id}/duplicate", status_code=201)
def duplicate_order(
    order_id: str,
    payload: DuplicateRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    try:
        row = _repo(engine).duplicate_production_order(
            order_id,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            new_order_number=payload.new_order_number,
            actor=context.user_id,
        )
        return _order(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class OrderCreate(BaseModel):
    order_number: str
    work_type: str
    requested_units: int = Field(ge=1)
    product_name: str
    product_format: str
    sku: str = ""
    customer_id: str | None = None
    due_date: date | None = None
    priority: str = "normal"
    source_lot_reference: str = ""
    material_owner: str = "internal"
    packaging_owner: str = "internal"
    notes: str = ""


@router.post("/orders", status_code=201)
def create_order(
    payload: OrderCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if not payload.order_number.strip() or not payload.product_name.strip():
        raise HTTPException(422, "Order number and product name are required.")
    try:
        row = _repo(engine).create_production_order(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            order_number=payload.order_number,
            work_type=payload.work_type,
            requested_units=payload.requested_units,
            product_name=payload.product_name,
            product_format=payload.product_format,
            sku=payload.sku,
            customer_id=payload.customer_id,
            due_at=datetime.combine(payload.due_date, time.min) if payload.due_date else None,
            priority=payload.priority,
            source_lot_reference=payload.source_lot_reference,
            material_owner=payload.material_owner,
            packaging_owner=payload.packaging_owner,
            notes=payload.notes,
            actor=context.user_id,
        )
        return _order(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class OptimizerRequest(BaseModel):
    bulk_weight: float = Field(ge=0)
    bulk_unit: str
    expected_loss_pct: float = Field(ge=0, le=50)
    optimization_goal: str
    labor_rate: float = Field(ge=0)
    products: list[dict]


@router.post("/optimizer")
def optimizer(
    payload: OptimizerRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    hand = _repo(engine).ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
    recommendations = recommend_weight_allocation(
        weight_to_grams(payload.bulk_weight, payload.bulk_unit),
        payload.products,
        loss_pct=payload.expected_loss_pct,
        labor_rate=payload.labor_rate,
        sticker_units_per_person_hour=hand.sticker_units_per_person_hour,
        case_pack_units_per_person_hour=hand.case_pack_units_per_person_hour,
        final_cases_per_person_hour=hand.final_cases_per_person_hour,
        optimization_goal=payload.optimization_goal,
    )
    usable_weight_g = weight_to_grams(payload.bulk_weight, payload.bulk_unit) * (1 - payload.expected_loss_pct / 100)
    return {
        "usable_weight_g": usable_weight_g,
        "rates_ready": all((hand.sticker_units_per_person_hour > 0, hand.case_pack_units_per_person_hour > 0, hand.final_cases_per_person_hour > 0)),
        "recommendations": recommendations,
    }


class PrefillRequest(BaseModel):
    recommendation: dict
    work_type_label: str


@router.post("/optimizer/prefill")
def optimizer_prefill(payload: PrefillRequest):
    result = build_recommended_order_prefill(payload.recommendation, payload.work_type_label)
    result["due_date"] = result["due_date"].isoformat()
    return result


class CustomerCreate(BaseModel):
    name: str
    license_or_registration: str = ""
    contact_name: str = ""
    contact_email: str = ""


@router.post("/customers", status_code=201)
def create_customer(payload: CustomerCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if not payload.name.strip():
        raise HTTPException(422, "Company name is required.")
    try:
        row = _repo(engine).create_customer(context.organization_id, **payload.model_dump())
        return {"id": row.id, **payload.model_dump()}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class MachineCreate(BaseModel):
    machine_model_id: str
    asset_code: str
    display_name: str
    effective_rate: float = Field(gt=0)
    preferred_crew_size: int = Field(ge=1)
    setup_minutes: int = Field(ge=0)
    cleanup_minutes: int = Field(ge=0)


@router.post("/machines", status_code=201)
def create_machine(payload: MachineCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if not payload.asset_code.strip() or not payload.display_name.strip():
        raise HTTPException(422, "Asset code and facility name are required.")
    try:
        row = _repo(engine).create_facility_machine(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id}
    except ValueError as exc:
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
    area = repo.ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
    try:
        row = repo.update_hand_labor_area(area.id, organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class ProductCreate(BaseModel):
    sku: str
    name: str
    item_type: str
    base_unit: str
    unit_cost: float = Field(ge=0)


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if not payload.sku.strip() or not payload.name.strip():
        raise HTTPException(422, "SKU and product name are required.")
    try:
        row = _repo(engine).create_product(context.organization_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class LotCreate(BaseModel):
    product_id: str
    lot_code: str
    compliance_package_id: str = ""
    location_code: str = "UNASSIGNED"
    opening_quantity: float = Field(ge=0)
    unit: str


@router.post("/lots", status_code=201)
def create_lot(payload: LotCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_inventory_lot(context.organization_id, context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class MovementCreate(BaseModel):
    lot_id: str
    transaction_type: str
    quantity: float = Field(gt=0)
    unit: str
    reason: str


@router.post("/movements", status_code=201)
def create_movement(payload: MovementCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    outbound = {"adjustment_out", "production_consume", "waste", "shipment"}
    transaction_type = "adjustment" if payload.transaction_type.startswith("adjustment_") else payload.transaction_type
    quantity_delta = -payload.quantity if payload.transaction_type in outbound else payload.quantity
    try:
        row = _repo(engine).post_inventory_transaction(context.organization_id, context.facility_id, lot_id=payload.lot_id, transaction_type=transaction_type, quantity_delta=quantity_delta, unit=payload.unit, reason=payload.reason, actor=context.user_id)
        return {"id": row.id}
    except ValueError as exc:
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
        return {"id": row.id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class BomCreate(BaseModel):
    output_product_id: str
    output_quantity: float = Field(gt=0)
    expected_loss_pct: float = Field(ge=0)
    components: list[dict]


@router.post("/boms", status_code=201)
def create_bom(payload: BomCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).create_bom(context.organization_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id, "version": row.version}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class CrewCreate(BaseModel):
    work_date: date
    shift_name: str
    available_people: int = Field(ge=0)
    shift_hours: float = Field(gt=0)
    notes: str = ""


@router.post("/crew")
def set_crew(payload: CrewCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).set_crew_availability(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class CapacityRequest(BaseModel):
    requested_units: int = Field(ge=0)
    effective_rate: float = Field(gt=0)
    crew_size: int = Field(ge=1)
    setup_minutes: int = Field(ge=0)
    cleanup_minutes: int = Field(ge=0)
    shift_hours: float = Field(gt=0)
    units_per_case: int = Field(ge=1)


@router.post("/capacity")
def capacity(payload: CapacityRequest, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    hand = repo.ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
    machine = estimate_machine_job(payload.requested_units, payload.effective_rate, payload.crew_size, payload.setup_minutes, payload.cleanup_minutes, payload.shift_hours)
    hand_ready = all((hand.sticker_units_per_person_hour > 0, hand.case_pack_units_per_person_hour > 0, hand.final_cases_per_person_hour > 0))
    hand_result = estimate_hand_labor_job(payload.requested_units, hand.default_crew_size, hand.sticker_units_per_person_hour, hand.case_pack_units_per_person_hour, hand.final_cases_per_person_hour, payload.units_per_case, hand.setup_minutes, hand.cleanup_minutes) if hand_ready else None
    return {"machine": machine, "hand": hand_result, "rates_ready": hand_ready}


class ActualCreate(BaseModel):
    actual_units: int = Field(ge=0)
    scrap_units: int = Field(ge=0)
    rework_units: int = Field(ge=0)
    actual_machine_hours: float = Field(ge=0)
    actual_labor_hours: float = Field(ge=0)
    notes: str = ""


@router.post("/orders/{order_id}/actuals")
def create_actual(order_id: str, payload: ActualCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).record_production_actual(order_id, organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/report.pdf")
def report_pdf(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    customers = repo.list_customers(context.organization_id)
    orders = repo.list_production_orders(context.organization_id, context.facility_id)
    actuals = repo.list_production_actuals(context.organization_id, context.facility_id)
    machines = repo.list_facility_machines(context.organization_id, context.facility_id)
    crew = repo.list_crew_availability(context.organization_id, context.facility_id, date.today())
    customers_by_id = {row.id: row for row in customers}
    orders_by_id = {row.id: row for row in orders}
    with Session(engine) as session:
        organization = session.get(Organization, context.organization_id)
        facility = session.get(Facility, context.facility_id)
    payload = {
        "organization": organization.name if organization else context.organization_id,
        "facility": facility.name if facility else context.facility_id,
        "reporting_period": f"Queue snapshot {datetime.now():%Y-%m-%d}",
        "orders": pd.DataFrame([{"Order": row.order_number, "Type": row.work_type.title(), "Customer": customers_by_id[row.customer_id].name if row.customer_id in customers_by_id else "Internal", "Product": row.product_name, "Format": row.product_format, "Units": row.requested_units, "Due": row.due_at.date().isoformat() if row.due_at else "Not set", "Priority": row.priority.title(), "Status": row.status.title(), "Source Lot": row.source_lot_reference} for row in orders]),
        "actuals": pd.DataFrame([{"Order": orders_by_id[row.production_order_id].order_number if row.production_order_id in orders_by_id else row.production_order_id, "Product": orders_by_id[row.production_order_id].product_name if row.production_order_id in orders_by_id else "Unknown", "Planned Units": orders_by_id[row.production_order_id].requested_units if row.production_order_id in orders_by_id else 0, "Actual Units": row.actual_units, "Attainment %": round(row.actual_units / orders_by_id[row.production_order_id].requested_units * 100, 1) if row.production_order_id in orders_by_id and orders_by_id[row.production_order_id].requested_units else 0, "Scrap": row.scrap_units, "Rework": row.rework_units, "Machine Hours": row.actual_machine_hours, "Labor Hours": row.actual_labor_hours, "Completed": row.completed_at} for row in actuals]),
        "machines": pd.DataFrame([{"Asset": row.asset_code, "Machine": row.display_name, "Effective Rate": row.effective_rate, "Rate Unit": row.rate_unit, "Preferred Crew": row.preferred_crew_size, "Setup Minutes": row.setup_minutes, "Cleanup Minutes": row.cleanup_minutes, "Active": row.active} for row in machines]),
        "crew": pd.DataFrame([{"Date": row.work_date, "Shift": row.shift_name, "People": row.available_people, "Shift Hours": row.shift_hours, "Available Labor Hours": row.available_people * row.shift_hours, "Notes": row.notes} for row in crew]),
        "customers": pd.DataFrame([{"Customer": row.name, "License / Registration": row.license_or_registration, "Contact": row.contact_name, "Email": row.contact_email, "Active": row.active} for row in customers]),
    }
    pdf = _build_coman_executive_report_pdf(payload)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="production_ops_coman_report.pdf"'})
