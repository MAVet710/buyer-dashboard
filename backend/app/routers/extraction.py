from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine
from modules.coman.repository import ComanRepository
from modules.extraction.repository import ExtractionRepository
from modules.extraction.traceability import ExtractionTraceabilityService
from modules.extraction.workflows import WORKFLOWS
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine
router = APIRouter(prefix="/extraction", tags=["extraction"], dependencies=[Depends(get_production_context)])

class RunCreate(BaseModel):
    batch_number: str; workflow_key: str; method: str; product_family: str = ""; strain: str = ""; operator: str = ""; compliance_provider: str = "metrc"; license_number: str = ""; production_order_id: str | None = None; toll_processing: bool = False; notes: str = ""
class ReserveInput(BaseModel): lot_id: str; quantity: float; role: str = "primary_input"; unit: str | None = None; source_reference: str = ""
class ConsumeInput(BaseModel): quantity: float; reason: str = "Extraction consumption"
class StageEvent(BaseModel):
    stage_key: str; event_type: str; input_weight_g: float | None = None; output_weight_g: float | None = None; loss_weight_g: float | None = None; loss_reason: str = ""; operator: str = ""; notes: str = ""
class OutputCreate(BaseModel):
    product_id: str; lot_code: str; quantity: float; output_label: str = ""; unit: str | None = None; compliance_package_id: str = ""; location_code: str = "WIP-EXTRACTION"; notes: str = ""
class CostCreate(BaseModel):
    category: str; amount_usd: float; quantity: float | None = None; unit: str = ""; unit_rate_usd: float | None = None; source_type: str = "manual"; source_id: str = ""; notes: str = ""
class QACreate(BaseModel):
    event_type: str; result: str; output_id: str | None = None; coa_reference: str = ""; deviation_code: str = ""; notes: str = ""
class NotesUpdate(BaseModel): notes: str = ""
class TraceabilityOutputCreate(BaseModel):
    output_id: str; new_tag: str; metrc_item_name: str = ""; location: str = ""; note: str = ""; is_finished_good: bool | None = None

def _repo(engine): return ExtractionRepository(engine)
def _run(row): return {key: getattr(row, key) for key in ("id", "batch_number", "method", "workflow_key", "current_stage_key", "status", "release_status", "product_family", "strain", "toll_processing", "compliance_provider", "license_number", "operator", "notes", "started_at", "completed_at", "updated_at")}
def _input(row): return {key: getattr(row, key) for key in ("id", "lot_id", "role", "planned_quantity", "reserved_quantity", "consumed_quantity", "unit", "input_cost_usd", "status")}
def _output(row): return {key: getattr(row, key) for key in ("id", "product_id", "lot_id", "position", "output_label", "quantity", "unit", "status", "coa_status", "compliance_package_id", "output_cost_usd")}

@router.get("/workflows")
def workflows(): return [{"key": row.key, "label": row.label, "method": row.method, "stages": [{"key": stage.key, "label": stage.label, "qa_gate": stage.qa_gate, "release_gate": stage.release_gate} for stage in row.stages]} for row in WORKFLOWS]
@router.get("/runs")
def runs(include_closed: bool = True, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)): return [_run(row) for row in _repo(engine).list_runs(context.organization_id, context.facility_id, include_closed=include_closed)]
@router.post("/runs", status_code=201)
def create_run(payload: RunCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _run(_repo(engine).create_run(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.get("/lots")
def lots(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)): return _repo(engine).list_available_lots(context.organization_id, context.facility_id)
@router.get("/products")
def products(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    rows = ComanRepository(engine).list_products(context.organization_id)
    return [{key: getattr(row, key) for key in ("id", "name", "sku", "item_type", "base_unit")} for row in rows if row.item_type in {"cannabis", "wip", "finished_good"}]
@router.get("/runs/{run_id}")
def detail(run_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    try:
        snapshot = repo.run_360(context.organization_id, context.facility_id, run_id)
        run = snapshot["run"]
        mass_balance = snapshot["mass_balance"]
        mass_balance["output_quantity"] = mass_balance["recorded_output"]
        workflow = snapshot["workflow"]
        toll = snapshot["toll_job"]
        return {
            "run": _run(run),
            "workflow": {"key": workflow.key, "label": workflow.label, "method": workflow.method, "stages": [{"key": row.key, "label": row.label, "qa_gate": row.qa_gate, "release_gate": row.release_gate} for row in workflow.stages]},
            "inputs": [_input(row) for row in snapshot["inputs"]],
            "outputs": [_output(row) for row in snapshot["outputs"]],
            "events": [{key: getattr(row, key) for key in ("id", "stage_key", "event_type", "input_weight_g", "output_weight_g", "loss_weight_g", "loss_reason", "operator", "notes", "occurred_at")} for row in snapshot["stages"]],
            "qa_events": [{key: getattr(row, key) for key in ("id", "output_id", "event_type", "result", "coa_reference", "deviation_code", "notes", "actor", "occurred_at")} for row in snapshot["qa_events"]],
            "cost_events": [{key: getattr(row, key) for key in ("id", "category", "amount_usd", "quantity", "unit", "unit_rate_usd", "source_type", "actor", "notes", "occurred_at")} for row in snapshot["cost_events"]],
            "traceability": [{key: getattr(row, key) for key in ("id", "provider", "operation_type", "status", "external_reference", "error_message", "requested_by", "requested_at")} for row in snapshot["traceability"]],
            "mass_balance": mass_balance,
            "cogs": snapshot["cogs"],
            "toll_job": None if toll is None else {key: getattr(toll, key) for key in ("id", "promised_completion_at", "processing_fee_usd", "invoice_status", "payment_status", "external_reference", "notes")},
        }
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
@router.post("/runs/{run_id}/notes")
def update_notes(run_id: str, payload: NotesUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _run(_repo(engine).update_run_notes(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, notes=payload.notes, actor=context.user_id))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/runs/{run_id}/inputs", status_code=201)
def reserve(run_id: str, payload: ReserveInput, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _input(_repo(engine).reserve_input(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/inputs/{input_id}/consume")
def consume(input_id: str, payload: ConsumeInput, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _input(_repo(engine).consume_input(organization_id=context.organization_id, facility_id=context.facility_id, run_input_id=input_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/inputs/{input_id}/release")
def release_input(input_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _input(_repo(engine).release_input_reservation(organization_id=context.organization_id, facility_id=context.facility_id, run_input_id=input_id, actor=context.user_id))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/runs/{run_id}/events", status_code=201)
def stage(run_id: str, payload: StageEvent, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).record_stage_event(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()); return {"id": row.id, "event_type": row.event_type, "stage_key": row.stage_key}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/runs/{run_id}/outputs", status_code=201)
def output(run_id: str, payload: OutputCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _output(_repo(engine).create_output(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/runs/{run_id}/costs", status_code=201)
def cost(run_id: str, payload: CostCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).add_cost_event(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()); return {"id": row.id, "category": row.category, "amount_usd": row.amount_usd}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/runs/{run_id}/qa", status_code=201)
def qa(run_id: str, payload: QACreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in {"dev", "admin", "supervisor", "qa"}: raise HTTPException(403, "Your role cannot post extraction QA decisions.")
    try:
        row = _repo(engine).record_qa_event(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()); return {"id": row.id, "event_type": row.event_type, "result": row.result}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
@router.post("/runs/{run_id}/traceability/output-package", status_code=201)
def queue_output_package(run_id: str, payload: TraceabilityOutputCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = ExtractionTraceabilityService(engine).queue_output_package_creation(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "provider", "operation_type", "status", "external_reference", "error_message", "requested_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
