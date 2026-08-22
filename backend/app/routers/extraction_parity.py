from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Customer
from modules.extraction.repository import ExtractionRepository
from modules.extraction.performance import ExtractionPerformanceService
from modules.extraction.workflows import default_workflow_for_method
from modules.data_hub_repository import MAX_DURABLE_UPLOAD_BYTES
from services.extraction_partner_import import DEFAULTS as PARTNER_DEFAULTS, TARGET_FIELDS as PARTNER_TARGET_FIELDS, apply_mapping as apply_partner_mapping, confidence as partner_confidence, normalize_workbook, suggestions as partner_suggestions
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine

router = APIRouter(prefix="/extraction-parity", tags=["extraction-parity"], dependencies=[Depends(get_production_context)])


class TollJobCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=255)
    state: str = Field(default="MA", max_length=64)
    license_or_registration: str = Field(default="", max_length=255)
    method: str = "BHO"
    batch_id_internal: str = ""
    metrc_transfer_id: str = ""
    promised_completion_at: datetime | None = None
    material_received_at: datetime | None = None
    input_weight_g: float = Field(default=0, ge=0)
    expected_output_g: float = Field(default=0, ge=0)
    actual_output_g: float = Field(default=0, ge=0)
    processing_fee_usd: float = Field(default=0, ge=0)
    invoice_status: str = "draft"
    payment_status: str = "pending"
    coa_status: str = "pending"
    job_status: str = "queued"
    notes: str = ""


class ManualRunCreate(BaseModel):
    run_date: date = Field(default_factory=date.today)
    state: str = "MA"
    license_name: str = ""
    client_name: str = "In House"
    batch_id_internal: str = Field(default="", max_length=120)
    method: str = "BHO"
    product_type: str = "Sugar"
    input_material_type: str = "Fresh Frozen"
    input_weight_g: float = Field(default=0, ge=0)
    intermediate_output_g: float = Field(default=0, ge=0)
    finished_output_g: float = Field(default=0, ge=0)
    residual_loss_g: float = Field(default=0, ge=0)
    operator: str = ""
    machine_line: str = ""
    metrc_package_id_input: str = ""
    metrc_package_id_output: str = ""
    metrc_manifest_or_transfer_id: str = ""
    coa_status: str = "Pending"
    qa_hold: bool = False
    toll_processing: bool = False
    processing_fee_usd: float = Field(default=0, ge=0)
    est_revenue_usd: float = Field(default=0, ge=0)
    cogs_usd: float = Field(default=0, ge=0)
    notes: str = ""
    status: str = "Complete"


def _repo(engine: Engine) -> ExtractionRepository:
    return ExtractionRepository(engine)


def _toll(row):
    if row is None:
        return None
    result = {key: getattr(row, key) for key in ("id", "run_id", "customer_id", "promised_completion_at", "processing_fee_usd", "invoice_status", "payment_status", "external_reference", "notes", "jurisdiction", "client_license_snapshot", "material_received_at", "input_weight_g", "expected_output_g", "actual_output_g", "coa_status", "job_status", "created_at", "updated_at")}
    for key in ("invoice_status", "payment_status", "coa_status", "job_status"):
        result[key] = str(result[key] or "").title()
    return result


@router.get("/overview")
def overview(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    runs = repo.list_runs(context.organization_id, context.facility_id, include_closed=True)
    rows = []
    finished = 0.0
    yields = []
    qa_holds = 0
    toll_jobs = 0
    total_cogs = 0.0
    total_revenue = 0.0
    performance = ExtractionPerformanceService(engine)
    for run in runs:
        mass = repo.mass_balance(context.organization_id, context.facility_id, run.id)
        cogs = repo.cogs_summary(context.organization_id, context.facility_id, run.id)
        toll = repo.get_toll_job(context.organization_id, context.facility_id, run.id)
        qa = repo.list_qa_events(context.organization_id, context.facility_id, run.id)
        trace = repo.list_traceability_transactions(context.organization_id, context.facility_id, run.id)
        input_weight = float(mass.get("consumed_input", 0)) or float(run.manual_input_weight_g or 0)
        output_weight = float(mass.get("recorded_output", 0)) or float(run.manual_finished_output_g or 0)
        yield_pct = output_weight / input_weight * 100 if input_weight else 0.0
        finished += output_weight
        yields.append(yield_pct)
        economics = performance.run_metrics(context.organization_id, context.facility_id, run.id)
        run_cogs = float(cogs.get("total", 0)) or float(run.manual_cogs_usd or 0)
        run_revenue = float(economics.get("projected_output_value", 0)) or float(run.estimated_revenue_usd or 0)
        total_cogs += run_cogs
        total_revenue += run_revenue
        qa_hold = bool(run.manual_qa_hold) or run.status == "hold" or any(event.result == "failed" for event in qa)
        qa_holds += int(qa_hold)
        toll_jobs += int(toll is not None or run.toll_processing)
        rows.append({
            "id": run.id,
            "batch_id_internal": run.manual_batch_id_internal if run.manual_batch_id_internal is not None else run.batch_number,
            "method": run.method,
            "product_type": run.product_family,
            "strain": run.strain,
            "operator": run.operator,
            "status": run.status.title(),
            "release_status": run.release_status,
            "toll_processing": run.toll_processing,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "run_date": run.run_date,
            "state": run.jurisdiction,
            "license_name": run.facility_license_name,
            "client_name": run.client_name_snapshot,
            "input_material_type": run.input_material_type,
            "intermediate_output_g": run.intermediate_output_g,
            "machine_line": run.machine_line,
            "metrc_package_id_input": run.metrc_package_id_input,
            "metrc_package_id_output": run.metrc_package_id_output,
            "metrc_manifest_or_transfer_id": run.metrc_manifest_or_transfer_id,
            "input_weight_g": input_weight,
            "finished_output_g": output_weight,
            "residual_loss_g": float(mass.get("unaccounted_balance", 0)) or float(run.residual_loss_g or 0),
            "yield_pct": yield_pct,
            "post_process_efficiency_pct": output_weight / float(run.intermediate_output_g or 0) * 100 if run.intermediate_output_g else 0.0,
            "processing_fee_usd": run.processing_fee_usd,
            "cogs_usd": run_cogs,
            "cost_per_output_unit": cogs.get("cost_per_output_unit", 0),
            "est_revenue_usd": run_revenue,
            "qa_hold": qa_hold,
            "coa_status": ("failed" if any(event.result == "failed" for event in qa) else "passed" if any(event.result == "passed" for event in qa) else run.manual_coa_status).title(),
            "notes": run.notes,
            "traceability_count": len(trace),
            "toll_job": _toll(toll),
        })
    alerts = []
    low = sum(1 for row in rows if row["input_weight_g"] > 0 and row["yield_pct"] < 12)
    if low:
        alerts.append(f"Low yield runs: {low} below 12% yield.")
    if qa_holds:
        alerts.append(f"QA holds active: {qa_holds} run(s).")
    pending = sum(1 for row in rows if str(row["coa_status"]).casefold() in {"pending", "failed"})
    if pending:
        alerts.append(f"COA risk: {pending} run(s) pending/failed.")
    return {"summary": {"runs": len(rows), "finished_output_g": finished, "avg_yield_pct": sum(yields) / len(yields) if yields else 0, "qa_holds": qa_holds, "total_revenue_usd": total_revenue, "total_cogs_usd": total_cogs, "toll_jobs": toll_jobs}, "alerts": alerts, "runs": rows}


@router.post("/runs", status_code=201)
def create_manual_run(payload: ManualRunCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    workflow = default_workflow_for_method(payload.method)
    durable_batch = f"MANUAL-{payload.run_date.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
    try:
        status = {"processing": "active", "queued": "queued", "complete": "complete", "hold": "hold", "failed": "failed"}.get(payload.status.strip().casefold(), "complete")
        release = "approved" if status == "complete" else "blocked" if status == "hold" else "rejected" if status == "failed" else "pending"
        row = _repo(engine).create_run(
            organization_id=context.organization_id, facility_id=context.facility_id,
            batch_number=durable_batch, method=workflow.method, workflow_key=workflow.key,
            actor=context.user_id, product_family=payload.product_type, operator=payload.operator,
            license_number=payload.license_name, toll_processing=payload.toll_processing, notes=payload.notes,
            run_date=payload.run_date, jurisdiction=payload.state, facility_license_name=payload.license_name,
            client_name_snapshot=payload.client_name, input_material_type=payload.input_material_type,
            manual_batch_id_internal=payload.batch_id_internal,
            manual_input_weight_g=payload.input_weight_g, intermediate_output_g=payload.intermediate_output_g,
            manual_finished_output_g=payload.finished_output_g, residual_loss_g=payload.residual_loss_g,
            machine_line=payload.machine_line, metrc_package_id_input=payload.metrc_package_id_input,
            metrc_package_id_output=payload.metrc_package_id_output,
            metrc_manifest_or_transfer_id=payload.metrc_manifest_or_transfer_id,
            manual_coa_status=payload.coa_status, manual_qa_hold=payload.qa_hold,
            processing_fee_usd=payload.processing_fee_usd, estimated_revenue_usd=payload.est_revenue_usd,
            manual_cogs_usd=payload.cogs_usd,
            initial_status=status, initial_release_status=release,
        )
        if payload.cogs_usd > 0:
            _repo(engine).add_cost_event(organization_id=context.organization_id, facility_id=context.facility_id, run_id=row.id, category="other", amount_usd=payload.cogs_usd, actor=context.user_id, notes="Manual Run Analytics entry")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": row.id, "batch_id_internal": payload.batch_id_internal, "status": row.status.title()}


def _partner_upload(payload: bytes, file: UploadFile):
    if not payload:
        raise HTTPException(422, "The extraction run file is empty.")
    if len(payload) > MAX_DURABLE_UPLOAD_BYTES:
        raise HTTPException(413, "Extraction run files must be 10 MB or smaller.")
    wrapped = BytesIO(payload)
    wrapped.name = file.filename or "extraction-runs.csv"
    return wrapped


@router.post("/partner-import/inspect")
async def inspect_partner_import(file: UploadFile = File(...)):
    wrapped = _partner_upload(await file.read(MAX_DURABLE_UPLOAD_BYTES + 1), file)
    try:
        frame, diagnostics = normalize_workbook(wrapped.getvalue(), wrapped.name)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, f"Could not read uploaded run log: {exc}") from exc
    if frame.empty:
        raise HTTPException(422, "No rows found in uploaded workbook.")
    proposals = partner_suggestions([str(column) for column in frame.columns])
    score = partner_confidence(proposals)
    diagnostics["mapping_confidence"] = score
    return {
        "filename": wrapped.name,
        "rows": len(frame),
        "columns": [str(column) for column in frame.columns],
        "suggestions": proposals,
        "mapping_confidence": score,
        "defaults": PARTNER_DEFAULTS,
        "target_fields": PARTNER_TARGET_FIELDS,
        "preview": json.loads(frame.head(100).to_json(orient="records", date_format="iso")),
        "diagnostics": diagnostics,
    }


@router.post("/partner-import/publish")
async def publish_partner_import(mapping_json: str = Form(...), defaults_json: str = Form(...), file: UploadFile = File(...), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    wrapped = _partner_upload(await file.read(MAX_DURABLE_UPLOAD_BYTES + 1), file)
    try:
        mapping = json.loads(mapping_json)
        defaults = json.loads(defaults_json)
        if not isinstance(mapping, dict) or not isinstance(defaults, dict):
            raise ValueError("Partner mapping and defaults must be objects.")
        frame, _diagnostics = normalize_workbook(wrapped.getvalue(), wrapped.name)
        invalid = [source for source in mapping.values() if str(source) != "IGNORE" and str(source) not in frame.columns]
        if invalid:
            raise ValueError("Mapped source column no longer exists: " + ", ".join(str(value) for value in invalid))
        mapped = apply_partner_mapping(frame, {str(key): str(value) for key, value in mapping.items()}, defaults)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = {
        f"{run.run_date.isoformat() if run.run_date else ''}|{str(run.manual_batch_id_internal or '')}|{run.method}"
        for run in _repo(engine).list_runs(context.organization_id, context.facility_id, include_closed=True)
    }
    added = 0
    duplicates = 0
    for record in mapped.to_dict("records"):
        run_date = date.fromisoformat(str(record.get("run_date"))) if str(record.get("run_date") or "") else date.today()
        key = f"{run_date.isoformat()}|{str(record.get('batch_id_internal') or '')}|{str(record.get('method') or 'BHO')}"
        if key in existing:
            duplicates += 1
            continue
        payload = ManualRunCreate(
            run_date=run_date,
            state=str(record.get("state") or "MA"),
            license_name=str(record.get("license_name") or ""),
            client_name=str(record.get("client_name") or "In House"),
            batch_id_internal=str(record.get("batch_id_internal") or ""),
            method=str(record.get("method") or "BHO"),
            product_type="Other",
            input_material_type="Other",
            input_weight_g=float(record.get("input_weight_g") or 0),
            intermediate_output_g=float(record.get("intermediate_output_g") or 0),
            finished_output_g=float(record.get("finished_output_g") or 0),
            residual_loss_g=float(record.get("residual_loss_g") or 0),
            operator=str(record.get("operator") or ""),
            machine_line=str(record.get("machine_line") or ""),
            coa_status=str(record.get("coa_status") or "Pending"),
            qa_hold=bool(record.get("qa_hold")),
            notes=str(record.get("notes") or ""),
            status=str(record.get("status") or "Processing"),
        )
        create_manual_run(payload, context, engine)
        existing.add(key)
        added += 1
    return {"added": added, "duplicates": duplicates, "rows": len(mapped), "filename": wrapped.name}


@router.get("/customers")
def customers(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    with Session(engine) as session:
        rows = list(session.scalars(select(Customer).where(Customer.organization_id == context.organization_id, Customer.active.is_(True)).order_by(Customer.name)))
    return [{"id": row.id, "name": row.name, "license_or_registration": row.license_or_registration, "contact_name": row.contact_name, "contact_email": row.contact_email} for row in rows]


@router.post("/toll-jobs", status_code=201)
def create_toll_job(payload: TollJobCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    workflow = default_workflow_for_method(payload.method)
    repo = _repo(engine)
    with Session(engine) as session, session.begin():
        customer = session.scalar(select(Customer).where(Customer.organization_id == context.organization_id, Customer.name == payload.client_name.strip()))
        if customer is None:
            customer = Customer(organization_id=context.organization_id, name=payload.client_name.strip(), license_or_registration=payload.license_or_registration.strip(), active=True)
            session.add(customer)
            session.flush()
        elif payload.license_or_registration.strip() and not customer.license_or_registration:
            customer.license_or_registration = payload.license_or_registration.strip()
        customer_id = customer.id
    batch = payload.batch_id_internal.strip() or f"TOLL-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
    try:
        run = repo.create_run(organization_id=context.organization_id, facility_id=context.facility_id, batch_number=batch, method=workflow.method, workflow_key=workflow.key, actor=context.user_id, product_family="Toll Processing", customer_id=customer_id, toll_processing=True, notes=payload.notes, jurisdiction=payload.state, client_name_snapshot=payload.client_name, manual_input_weight_g=payload.input_weight_g, manual_finished_output_g=payload.actual_output_g, metrc_manifest_or_transfer_id=payload.metrc_transfer_id, manual_coa_status=payload.coa_status, processing_fee_usd=payload.processing_fee_usd)
        toll = repo.upsert_toll_job(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run.id, customer_id=customer_id, actor=context.user_id, promised_completion_at=payload.promised_completion_at, processing_fee_usd=payload.processing_fee_usd, invoice_status=payload.invoice_status, payment_status=payload.payment_status, external_reference=payload.metrc_transfer_id, notes=payload.notes, jurisdiction=payload.state, client_license_snapshot=payload.license_or_registration, material_received_at=payload.material_received_at, input_weight_g=payload.input_weight_g, expected_output_g=payload.expected_output_g, actual_output_g=payload.actual_output_g, coa_status=payload.coa_status, job_status=payload.job_status)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"run_id": run.id, "batch_id_internal": run.batch_number, "toll_job": _toll(toll)}


@router.get("/runs/{run_id}/compliance")
def compliance(run_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repo = _repo(engine)
    try:
        run = repo.get_run(context.organization_id, context.facility_id, run_id)
        outputs = repo.list_outputs(context.organization_id, context.facility_id, run_id)
        qa = repo.list_qa_events(context.organization_id, context.facility_id, run_id)
        trace = repo.list_traceability_transactions(context.organization_id, context.facility_id, run_id)
        toll = repo.get_toll_job(context.organization_id, context.facility_id, run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "run": {"id": run.id, "batch_number": run.batch_number, "method": run.method, "status": run.status, "release_status": run.release_status, "license_number": run.license_number, "compliance_provider": run.compliance_provider, "toll_processing": run.toll_processing},
        "outputs": [{"id": row.id, "output_label": row.output_label, "compliance_package_id": row.compliance_package_id, "coa_status": row.coa_status, "status": row.status} for row in outputs],
        "qa_events": [{"event_type": row.event_type, "result": row.result, "coa_reference": row.coa_reference, "deviation_code": row.deviation_code, "notes": row.notes, "occurred_at": row.occurred_at} for row in qa],
        "traceability": [{"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id, "status": row.status, "operation_type": row.operation_type, "requested_at": row.requested_at} for row in trace],
        "toll_job": _toll(toll),
    }
