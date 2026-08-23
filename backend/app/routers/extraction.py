from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.repository import ComanRepository
from modules.extraction.models import ExtractionRun, ExtractionStageEvent
from modules.extraction.repository import ExtractionRepository
from modules.extraction.traceability import ExtractionTraceabilityService
from modules.extraction.workflows import (
    TERPENE_HANDLING_MODES,
    WORKFLOWS,
    calculate_final_output_g,
    calculate_terpene_weight_g,
    get_extraction_workflow,
    method_aware_stage_fields,
)
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine

router = APIRouter(prefix="/extraction", tags=["extraction"], dependencies=[Depends(get_production_context)])

RUN_STAGE_OUTPUT_FIELDS = (
    "extraction_output_g",
    "purge_output_g",
    "crystallization_output_g",
    "sauce_fraction_g",
    "diamond_fraction_g",
    "crude_output_g",
    "winterized_output_g",
    "filtered_output_g",
    "decarbed_output_g",
    "distillate_output_g",
    "wash_output_g",
    "dried_hash_output_g",
    "sift_output_g",
    "rosin_output_g",
)


class RunCreate(BaseModel):
    batch_number: str
    workflow_key: str
    method: str
    product_family: str = ""
    strain: str = ""
    operator: str = ""
    compliance_provider: str = "metrc"
    license_number: str = ""
    production_order_id: str | None = None
    toll_processing: bool = False
    notes: str = ""
    intermediate_product_type: str = ""
    final_product_type: str = ""
    formulation_used: bool = False
    formulation_base_g: float = 0.0
    terpene_handling_mode: str = "Native / No Add-Back"
    terpene_type: str = ""
    terpene_source: str = ""
    terpene_percentage: float = 0.0
    terpene_weight_g: float | None = None
    metrc_input_package_id: str = ""
    metrc_intermediate_package_id: str = ""
    metrc_distillate_package_id: str = ""
    metrc_formulation_package_id: str = ""
    metrc_final_package_id: str = ""


class ReserveInput(BaseModel):
    lot_id: str
    quantity: float
    role: str = "primary_input"
    unit: str | None = None
    source_reference: str = ""


class ConsumeInput(BaseModel):
    quantity: float
    reason: str = "Extraction consumption"


class StageEvent(BaseModel):
    stage_key: str
    event_type: str
    input_weight_g: float | None = None
    output_weight_g: float | None = None
    loss_weight_g: float | None = None
    loss_reason: str = ""
    operator: str = ""
    notes: str = ""
    stage_output_field: str = ""
    metrc_stage_input_id: str = ""
    metrc_stage_output_id: str = ""
    intermediate_product_type: str | None = None
    final_product_type: str | None = None
    formulation_used: bool | None = None
    formulation_base_g: float | None = None
    terpene_handling_mode: str | None = None
    terpene_type: str | None = None
    terpene_source: str | None = None
    terpene_percentage: float | None = None
    terpene_weight_g: float | None = None


class OutputCreate(BaseModel):
    product_id: str
    lot_code: str
    quantity: float
    output_label: str = ""
    unit: str | None = None
    compliance_package_id: str = ""
    location_code: str = "WIP-EXTRACTION"
    notes: str = ""


class CostCreate(BaseModel):
    category: str
    amount_usd: float
    quantity: float | None = None
    unit: str = ""
    unit_rate_usd: float | None = None
    source_type: str = "manual"
    source_id: str = ""
    notes: str = ""


class QACreate(BaseModel):
    event_type: str
    result: str
    output_id: str | None = None
    coa_reference: str = ""
    deviation_code: str = ""
    notes: str = ""


class NotesUpdate(BaseModel):
    notes: str = ""


class TraceabilityOutputCreate(BaseModel):
    output_id: str
    new_tag: str
    metrc_item_name: str = ""
    location: str = ""
    note: str = ""
    is_finished_good: bool | None = None


def _repo(engine):
    return ExtractionRepository(engine)


def _run(row):
    keys = (
        "id",
        "batch_number",
        "method",
        "workflow_key",
        "current_stage_key",
        "status",
        "release_status",
        "product_family",
        "strain",
        "toll_processing",
        "compliance_provider",
        "license_number",
        "operator",
        "notes",
        "intermediate_product_type",
        "final_product_type",
        "formulation_used",
        "formulation_base_g",
        "terpene_handling_mode",
        "terpene_type",
        "terpene_source",
        "terpene_percentage",
        "terpene_weight_g",
        "final_output_g",
        "metrc_input_package_id",
        "metrc_intermediate_package_id",
        "metrc_distillate_package_id",
        "metrc_formulation_package_id",
        "metrc_final_package_id",
        *RUN_STAGE_OUTPUT_FIELDS,
        "started_at",
        "completed_at",
        "updated_at",
    )
    return {key: getattr(row, key) for key in keys}


def _input(row):
    return {key: getattr(row, key) for key in ("id", "lot_id", "role", "planned_quantity", "reserved_quantity", "consumed_quantity", "unit", "input_cost_usd", "status")}


def _output(row):
    return {key: getattr(row, key) for key in ("id", "product_id", "lot_id", "position", "output_label", "quantity", "unit", "status", "coa_status", "compliance_package_id", "output_cost_usd")}


def _stage_outputs(run: ExtractionRun, extra: dict | None = None) -> dict[str, float]:
    values = {field: float(getattr(run, field, 0.0) or 0.0) for field in RUN_STAGE_OUTPUT_FIELDS}
    if extra:
        values.update(extra)
    return values


def _apply_formulation_fields(run: ExtractionRun, values: dict, *, explicit_finished_output_g: float | None = None) -> None:
    for key in ("intermediate_product_type", "final_product_type", "terpene_type", "terpene_source"):
        if key in values and values[key] is not None:
            setattr(run, key, str(values[key] or "").strip())

    if values.get("formulation_used") is not None:
        run.formulation_used = bool(values["formulation_used"])
    if values.get("formulation_base_g") is not None:
        run.formulation_base_g = max(0.0, float(values["formulation_base_g"] or 0.0))

    if values.get("terpene_handling_mode") is not None:
        mode = str(values["terpene_handling_mode"] or "Native / No Add-Back").strip()
        if mode not in TERPENE_HANDLING_MODES:
            raise ValueError("Unsupported terpene handling mode.")
        run.terpene_handling_mode = mode

    if values.get("terpene_percentage") is not None:
        run.terpene_percentage = float(values["terpene_percentage"] or 0.0)

    manual_weight_supplied = "terpene_weight_g" in values and values.get("terpene_weight_g") is not None
    manual_weight = values.get("terpene_weight_g") if manual_weight_supplied else None
    if run.terpene_handling_mode == "Native / No Add-Back":
        run.terpene_weight_g = 0.0
    elif manual_weight_supplied or values.get("terpene_percentage") is not None or values.get("formulation_base_g") is not None:
        run.terpene_weight_g = calculate_terpene_weight_g(
            run.formulation_base_g,
            run.terpene_percentage,
            manual_weight,
        )

    for key in (
        "metrc_input_package_id",
        "metrc_intermediate_package_id",
        "metrc_distillate_package_id",
        "metrc_formulation_package_id",
        "metrc_final_package_id",
    ):
        if key in values and values[key] is not None:
            setattr(run, key, str(values[key] or "").strip())

    for field in RUN_STAGE_OUTPUT_FIELDS:
        if field in values and values[field] is not None:
            setattr(run, field, max(0.0, float(values[field] or 0.0)))

    run.final_output_g = calculate_final_output_g(
        run.workflow_key,
        _stage_outputs(run),
        formulation_used=run.formulation_used,
        formulation_base_g=run.formulation_base_g,
        terpene_weight_g=run.terpene_weight_g,
        explicit_finished_output_g=explicit_finished_output_g,
    )


def _persist_run_enhancements(engine: Engine, context: RequestContext, run_id: str, values: dict) -> ExtractionRun:
    with Session(engine) as session:
        run = session.get(ExtractionRun, run_id)
        if not run or run.organization_id != context.organization_id or run.facility_id != context.facility_id:
            raise ValueError("Extraction run was not found in the active facility.")
        _apply_formulation_fields(run, values)
        run.updated_by = context.user_id
        session.commit()
        session.refresh(run)
        return run


def _persist_stage_enhancements(engine: Engine, context: RequestContext, run_id: str, event_id: str, payload: StageEvent) -> None:
    with Session(engine) as session:
        run = session.get(ExtractionRun, run_id)
        event = session.get(ExtractionStageEvent, event_id)
        if not run or run.organization_id != context.organization_id or run.facility_id != context.facility_id:
            raise ValueError("Extraction run was not found in the active facility.")
        if not event or event.run_id != run.id:
            raise ValueError("Extraction stage event was not found.")

        workflow = get_extraction_workflow(run.workflow_key)
        stage_definition = workflow.stage(payload.stage_key)
        if stage_definition is None:
            raise ValueError("Stage is not valid for this extraction workflow.")

        output_field = payload.stage_output_field.strip()
        allowed_fields = set(stage_definition.output_fields)
        if output_field and output_field not in allowed_fields:
            raise ValueError("Stage output field is not valid for this workflow stage.")

        event.stage_output_field = output_field
        event.metrc_stage_input_id = payload.metrc_stage_input_id.strip()
        event.metrc_stage_output_id = payload.metrc_stage_output_id.strip()

        values = payload.model_dump(
            include={
                "intermediate_product_type",
                "final_product_type",
                "formulation_used",
                "formulation_base_g",
                "terpene_handling_mode",
                "terpene_type",
                "terpene_source",
                "terpene_percentage",
                "terpene_weight_g",
            },
            exclude_none=True,
        )
        if payload.stage_key == "formulation" and "formulation_used" not in values:
            values["formulation_used"] = True
        if output_field and payload.output_weight_g is not None:
            values[output_field] = payload.output_weight_g

        _apply_formulation_fields(run, values)
        extra = {}
        if payload.output_weight_g is not None and payload.stage_key in {"formulation", "filling", "packaging", "final_output"}:
            extra[payload.stage_key] = max(0.0, float(payload.output_weight_g))
        run.final_output_g = calculate_final_output_g(
            run.workflow_key,
            _stage_outputs(run, extra),
            formulation_used=run.formulation_used,
            formulation_base_g=run.formulation_base_g,
            terpene_weight_g=run.terpene_weight_g,
            explicit_finished_output_g=(payload.output_weight_g if payload.stage_key == "final_output" else None),
        )
        run.updated_by = context.user_id
        session.commit()


@router.get("/workflows")
def workflows():
    return [
        {
            "key": row.key,
            "label": row.label,
            "method": row.method,
            "method_output_fields": list(method_aware_stage_fields(row.method)),
            "stages": [
                {
                    "key": stage.key,
                    "label": stage.label,
                    "qa_gate": stage.qa_gate,
                    "release_gate": stage.release_gate,
                    "optional": stage.optional,
                    "output_fields": list(stage.output_fields),
                }
                for stage in row.stages
            ],
        }
        for row in WORKFLOWS
    ]


@router.get("/runs")
def runs(include_closed: bool = True, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return [_run(row) for row in _repo(engine).list_runs(context.organization_id, context.facility_id, include_closed=include_closed)]


@router.post("/runs", status_code=201)
def create_run(payload: RunCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    base_fields = payload.model_dump(
        include={
            "batch_number",
            "workflow_key",
            "method",
            "product_family",
            "strain",
            "operator",
            "compliance_provider",
            "license_number",
            "production_order_id",
            "toll_processing",
            "notes",
        }
    )
    enhancement_fields = payload.model_dump(exclude=set(base_fields), exclude_none=True)
    try:
        row = _repo(engine).create_run(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
            **base_fields,
        )
        if enhancement_fields:
            row = _persist_run_enhancements(engine, context, row.id, enhancement_fields)
        return _run(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/lots")
def lots(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return _repo(engine).list_available_lots(context.organization_id, context.facility_id)


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
            "workflow": {
                "key": workflow.key,
                "label": workflow.label,
                "method": workflow.method,
                "method_output_fields": list(method_aware_stage_fields(workflow.method)),
                "stages": [
                    {
                        "key": row.key,
                        "label": row.label,
                        "qa_gate": row.qa_gate,
                        "release_gate": row.release_gate,
                        "optional": row.optional,
                        "output_fields": list(row.output_fields),
                    }
                    for row in workflow.stages
                ],
            },
            "inputs": [_input(row) for row in snapshot["inputs"]],
            "outputs": [_output(row) for row in snapshot["outputs"]],
            "events": [
                {
                    key: getattr(row, key)
                    for key in (
                        "id",
                        "stage_key",
                        "event_type",
                        "input_weight_g",
                        "output_weight_g",
                        "loss_weight_g",
                        "loss_reason",
                        "stage_output_field",
                        "metrc_stage_input_id",
                        "metrc_stage_output_id",
                        "operator",
                        "notes",
                        "occurred_at",
                    )
                }
                for row in snapshot["stages"]
            ],
            "qa_events": [{key: getattr(row, key) for key in ("id", "output_id", "event_type", "result", "coa_reference", "deviation_code", "notes", "actor", "occurred_at")} for row in snapshot["qa_events"]],
            "cost_events": [{key: getattr(row, key) for key in ("id", "category", "amount_usd", "quantity", "unit", "unit_rate_usd", "source_type", "actor", "notes", "occurred_at")} for row in snapshot["cost_events"]],
            "traceability": [{key: getattr(row, key) for key in ("id", "provider", "operation_type", "status", "external_reference", "error_message", "requested_by", "requested_at")} for row in snapshot["traceability"]],
            "mass_balance": mass_balance,
            "cogs": snapshot["cogs"],
            "toll_job": None if toll is None else {key: getattr(toll, key) for key in ("id", "promised_completion_at", "processing_fee_usd", "invoice_status", "payment_status", "external_reference", "notes")},
        }
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/runs/{run_id}/notes")
def update_notes(run_id: str, payload: NotesUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        return _run(_repo(engine).update_run_notes(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, notes=payload.notes, actor=context.user_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs/{run_id}/inputs", status_code=201)
def reserve(run_id: str, payload: ReserveInput, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        return _input(_repo(engine).reserve_input(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/inputs/{input_id}/consume")
def consume(input_id: str, payload: ConsumeInput, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        return _input(_repo(engine).consume_input(organization_id=context.organization_id, facility_id=context.facility_id, run_input_id=input_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/inputs/{input_id}/release")
def release_input(input_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        return _input(_repo(engine).release_input_reservation(organization_id=context.organization_id, facility_id=context.facility_id, run_input_id=input_id, actor=context.user_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs/{run_id}/events", status_code=201)
def stage(run_id: str, payload: StageEvent, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    generic = payload.model_dump(
        include={
            "stage_key",
            "event_type",
            "input_weight_g",
            "output_weight_g",
            "loss_weight_g",
            "loss_reason",
            "operator",
            "notes",
        }
    )
    try:
        row = _repo(engine).record_stage_event(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            run_id=run_id,
            actor=context.user_id,
            **generic,
        )
        _persist_stage_enhancements(engine, context, run_id, row.id, payload)
        return {
            "id": row.id,
            "event_type": row.event_type,
            "stage_key": row.stage_key,
            "stage_output_field": payload.stage_output_field,
            "metrc_stage_input_id": payload.metrc_stage_input_id,
            "metrc_stage_output_id": payload.metrc_stage_output_id,
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs/{run_id}/outputs", status_code=201)
def output(run_id: str, payload: OutputCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        return _output(_repo(engine).create_output(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs/{run_id}/costs", status_code=201)
def cost(run_id: str, payload: CostCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = _repo(engine).add_cost_event(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id, "category": row.category, "amount_usd": row.amount_usd}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs/{run_id}/qa", status_code=201)
def qa(run_id: str, payload: QACreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in {"dev", "admin", "supervisor", "qa"}:
        raise HTTPException(403, "Your role cannot post extraction QA decisions.")
    try:
        row = _repo(engine).record_qa_event(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id, "event_type": row.event_type, "result": row.result}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs/{run_id}/traceability/output-package", status_code=201)
def queue_output_package(run_id: str, payload: TraceabilityOutputCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = ExtractionTraceabilityService(engine).queue_output_package_creation(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "provider", "operation_type", "status", "external_reference", "error_message", "requested_at")}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc