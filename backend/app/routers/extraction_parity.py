from __future__ import annotations

from datetime import datetime
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Customer
from modules.extraction.repository import ExtractionRepository
from modules.extraction.workflows import default_workflow_for_method
from ..auth import RequestContext, get_request_context, get_production_context
from ..database import get_engine

router = APIRouter(prefix="/extraction-parity", tags=["extraction-parity"], dependencies=[Depends(get_production_context)])


class TollJobCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=255)
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


def _repo(engine: Engine) -> ExtractionRepository:
    return ExtractionRepository(engine)


def _toll(row):
    if row is None:
        return None
    return {key: getattr(row, key) for key in ("id", "run_id", "customer_id", "promised_completion_at", "processing_fee_usd", "invoice_status", "payment_status", "external_reference", "notes", "created_at", "updated_at")}


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
    for run in runs:
        mass = repo.mass_balance(context.organization_id, context.facility_id, run.id)
        cogs = repo.cogs_summary(context.organization_id, context.facility_id, run.id)
        toll = repo.get_toll_job(context.organization_id, context.facility_id, run.id)
        qa = repo.list_qa_events(context.organization_id, context.facility_id, run.id)
        trace = repo.list_traceability_transactions(context.organization_id, context.facility_id, run.id)
        finished += float(mass.get("recorded_output", 0))
        yields.append(float(mass.get("yield_pct", 0)))
        total_cogs += float(cogs.get("total", 0))
        qa_hold = run.status == "hold" or any(event.result == "failed" for event in qa)
        qa_holds += int(qa_hold)
        toll_jobs += int(toll is not None or run.toll_processing)
        rows.append({
            "id": run.id,
            "batch_id_internal": run.batch_number,
            "method": run.method,
            "product_type": run.product_family,
            "strain": run.strain,
            "operator": run.operator,
            "status": run.status,
            "release_status": run.release_status,
            "toll_processing": run.toll_processing,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "input_weight_g": mass.get("consumed_input", 0),
            "finished_output_g": mass.get("recorded_output", 0),
            "residual_loss_g": mass.get("unaccounted_balance", 0),
            "yield_pct": mass.get("yield_pct", 0),
            "cogs_usd": cogs.get("total", 0),
            "cost_per_output_unit": cogs.get("cost_per_output_unit", 0),
            "qa_hold": qa_hold,
            "coa_status": "failed" if any(event.result == "failed" for event in qa) else "passed" if any(event.result == "passed" for event in qa) else "pending",
            "traceability_count": len(trace),
            "toll_job": _toll(toll),
        })
    alerts = []
    low = sum(1 for row in rows if row["input_weight_g"] > 0 and row["yield_pct"] < 12)
    if low:
        alerts.append(f"Low yield runs: {low} below 12% yield.")
    if qa_holds:
        alerts.append(f"QA holds active: {qa_holds} run(s).")
    pending = sum(1 for row in rows if row["coa_status"] in {"pending", "failed"})
    if pending:
        alerts.append(f"COA risk: {pending} run(s) pending/failed.")
    return {"summary": {"runs": len(rows), "finished_output_g": finished, "avg_yield_pct": sum(yields) / len(yields) if yields else 0, "qa_holds": qa_holds, "total_cogs_usd": total_cogs, "toll_jobs": toll_jobs}, "alerts": alerts, "runs": rows}


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
    notes = json.dumps({"material_received_at": payload.material_received_at.isoformat() if payload.material_received_at else None, "input_weight_g": payload.input_weight_g, "expected_output_g": payload.expected_output_g, "actual_output_g": payload.actual_output_g, "coa_status": payload.coa_status, "job_status": payload.job_status, "notes": payload.notes}, sort_keys=True)
    try:
        run = repo.create_run(organization_id=context.organization_id, facility_id=context.facility_id, batch_number=batch, method=workflow.method, workflow_key=workflow.key, actor=context.user_id, product_family="Toll Processing", customer_id=customer_id, toll_processing=True, notes=payload.notes)
        toll = repo.upsert_toll_job(organization_id=context.organization_id, facility_id=context.facility_id, run_id=run.id, customer_id=customer_id, actor=context.user_id, promised_completion_at=payload.promised_completion_at, processing_fee_usd=payload.processing_fee_usd, invoice_status=payload.invoice_status, payment_status=payload.payment_status, external_reference=payload.metrc_transfer_id, notes=notes)
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
