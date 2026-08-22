from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine

from modules.production_erp.service import ProductionERPService
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine

router = APIRouter(prefix="/production", tags=["production"], dependencies=[Depends(get_production_context)])

class RunEventCreate(BaseModel):
    event_type: str
    stage_key: str = "execution"
    quantity: float | None = None
    unit: str = "unit"
    waste_quantity: float | None = None
    labor_hours: float | None = None
    machine_hours: float | None = None
    notes: str = ""
class OutputCreate(BaseModel):
    product_id: str; planned_quantity: float; label: str = ""; unit: str = "unit"
class OutputActual(BaseModel):
    actual_quantity: float; lot_code: str = ""
class QAEventCreate(BaseModel):
    event_type: str; result: str = "pending"; output_id: str | None = None; document_reference: str = ""; notes: str = ""
class CostCreate(BaseModel):
    category: str; amount_usd: float; quantity: float | None = None; unit: str = ""; source_type: str = "manual"; source_id: str = ""; notes: str = ""

def _service(engine: Engine) -> ProductionERPService:
    return ProductionERPService(engine)

@router.get("/orders")
def queue(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return _service(engine).queue_summary(context.organization_id, context.facility_id)

@router.get("/orders/{order_id}")
def order_360(order_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        snapshot = _service(engine).order_360(context.organization_id, context.facility_id, order_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    order = snapshot["order"]
    return {
        "order": {key: getattr(order, key) for key in ("id", "order_number", "product_name", "sku", "product_format", "requested_units", "priority", "status", "notes", "due_at")},
        "requirements": snapshot["requirements"],
        "reservations": [{key: getattr(row, key) for key in ("id", "lot_id", "quantity", "unit", "status")} for row in snapshot["reservations"]],
        "outputs": [{key: getattr(row, key) for key in ("id", "label", "planned_quantity", "actual_quantity", "unit", "status", "lot_id")} for row in snapshot["outputs"]],
        "events": [{key: getattr(row, key) for key in ("id", "stage_key", "event_type", "quantity", "unit", "waste_quantity", "labor_hours", "machine_hours", "notes", "actor", "occurred_at")} for row in snapshot["events"]],
        "qa_events": [{key: getattr(row, key) for key in ("id", "event_type", "result", "notes", "actor", "occurred_at")} for row in snapshot["qa_events"]],
        "cogs": snapshot["cogs"], "planned_output": snapshot["planned_output"], "actual_output": snapshot["actual_output"], "attainment_pct": snapshot["attainment_pct"],
    }

@router.post("/orders/{order_id}/reserve")
def reserve(order_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        return _service(engine).reserve_bom_materials(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/events", status_code=201)
def record_event(order_id: str, payload: RunEventCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        event = _service(engine).record_event(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(event, key) for key in ("id", "event_type", "stage_key", "quantity", "unit", "waste_quantity", "labor_hours", "machine_hours", "notes", "occurred_at")}
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/outputs", status_code=201)
def add_output(order_id: str, payload: OutputCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _service(engine).add_output(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "label", "planned_quantity", "actual_quantity", "unit", "status", "lot_id")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/outputs/{output_id}/actual")
def record_output(output_id: str, payload: OutputActual, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _service(engine).record_output_actual(organization_id=context.organization_id, facility_id=context.facility_id, output_id=output_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "label", "planned_quantity", "actual_quantity", "unit", "status", "lot_id")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/qa", status_code=201)
def record_qa(order_id: str, payload: QAEventCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in {"dev", "admin", "supervisor", "qa"}: raise HTTPException(403, "Your role cannot post QA decisions.")
    try:
        row = _service(engine).record_qa(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "event_type", "result", "output_id", "document_reference", "notes", "actor", "occurred_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/orders/{order_id}/costs", status_code=201)
def add_cost(order_id: str, payload: CostCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _service(engine).add_cost(organization_id=context.organization_id, facility_id=context.facility_id, order_id=order_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "category", "amount_usd", "quantity", "unit", "source_type", "source_id", "notes", "actor", "occurred_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
