from hashlib import sha256
from io import BytesIO
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, Facility, FacilityMachine
from modules.data_hub_core import DATASET_REQUIREMENTS, RETAIL_DATASETS, build_mapped_upload, inspect_uploaded_dataset
from modules.data_hub_repository import DataHubRepository, MAX_DURABLE_UPLOAD_BYTES
from modules.extraction.models import ExtractionRun
from modules.product_master.models import ProductMasterProfile
from services.data_mapping_agent import record_approved_mappings, suggest_column_mapping
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.ai_runtime import build_runtime

router = APIRouter(prefix="/data-hub", tags=["data-hub"])
SPECS = {str(spec["dataset_key"]): spec for spec in RETAIL_DATASETS}
PUBLISH_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}


class MappingSuggestionRequest(BaseModel):
    dataset_key: str
    columns: list[str] = Field(min_length=1, max_length=500)
    existing_matches: dict[str, str] = Field(default_factory=dict)
    source_vendor: str = Field(default="", max_length=255)


def _history(row):
    return {key: getattr(row, key) for key in ("id", "dataset_key", "dataset_label", "filename", "content_type", "fingerprint", "payload_size", "row_count", "column_count", "quality", "status", "imported_by", "activated_at", "created_at")} | {"mapping": json.loads(row.mapping_json or "{}"), "missing_fields": json.loads(row.missing_fields_json or "[]")}


def _spec(dataset_key: str):
    spec = SPECS.get(dataset_key)
    if not spec:
        raise HTTPException(422, "Unsupported Data Hub dataset.")
    return spec


def _wrapped(payload: bytes, file: UploadFile, label: str):
    if not payload:
        raise HTTPException(422, "The source file is empty.")
    if len(payload) > MAX_DURABLE_UPLOAD_BYTES:
        raise HTTPException(413, "The source file exceeds the 10 MB durable upload limit.")
    wrapped = BytesIO(payload)
    wrapped.name = file.filename or label
    wrapped.type = file.content_type or ""
    return wrapped


@router.get("/datasets")
def datasets(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    history = DataHubRepository(engine).list_history(context.organization_id, context.facility_id)
    active = {row.dataset_key: row for row in history if row.status == "active"}
    status_rows = []
    for spec in RETAIL_DATASETS:
        source = active.get(str(spec["dataset_key"]))
        status_rows.append({"operations": "Retail Ops", "dataset": spec["label"], "status": "Ready" if source else "Not loaded", "source": source.filename if source else "", "rows": source.row_count if source else 0, "updated": source.activated_at if source else None})
    with Session(engine) as session:
        facility = session.get(Facility, context.facility_id)
        extraction_runs = int(session.scalar(select(func.count()).select_from(ExtractionRun).where(ExtractionRun.organization_id == context.organization_id, ExtractionRun.facility_id == context.facility_id)) or 0)
        orders = int(session.scalar(select(func.count()).select_from(CommercialOrder).where(CommercialOrder.organization_id == context.organization_id, CommercialOrder.facility_id == context.facility_id)) or 0)
        nomenclature = int(session.scalar(select(func.count()).select_from(ProductMasterProfile).where(ProductMasterProfile.organization_id == context.organization_id)) or 0)
        capacity = int(session.scalar(select(func.count()).select_from(FacilityMachine).where(FacilityMachine.organization_id == context.organization_id, FacilityMachine.facility_id == context.facility_id)) or 0)
    compliance = active.get("compliance_sources") or active.get("sandbox_compliance_sources")
    status_rows.extend([
        {"operations": "Production Ops", "dataset": "Extraction Runs", "status": "Ready" if extraction_runs else "Not loaded", "source": "Durable production runs" if extraction_runs else "", "rows": extraction_runs, "updated": None},
        {"operations": "Production Ops", "dataset": "Co-Man Master Data", "status": "Ready", "source": facility.name if facility else context.facility_id, "rows": "Durable Supabase records", "updated": None},
        {"operations": "Commercial Ops", "dataset": "Orders & Fulfillment", "status": "Ready" if orders else "Not loaded", "source": "Durable order ledger" if orders else "", "rows": orders, "updated": None},
        {"operations": "Retail Ops", "dataset": "Nomenclature Catalog", "status": "Ready" if nomenclature else "Not loaded", "source": "Organization product catalog" if nomenclature else "", "rows": nomenclature, "updated": None},
        {"operations": "Production Ops", "dataset": "Production Capacity", "status": "Ready" if capacity else "Not loaded", "source": "Machines, hand labor, and crew plan" if capacity else "", "rows": capacity, "updated": None},
        {"operations": "Retail Ops", "dataset": "Compliance Sources", "status": "Ready" if compliance else "Not loaded", "source": compliance.filename if compliance else "", "rows": compliance.row_count if compliance else 0, "updated": compliance.activated_at if compliance else None},
    ])
    return {"catalog": [{key: spec[key] for key in ("label", "dataset_key", "description", "types")} for spec in RETAIL_DATASETS], "history": [_history(row) for row in history], "status": status_rows, "extraction_runs": extraction_runs}


@router.post("/datasets", status_code=201)
async def upload_dataset(dataset_key: str = Form(...), file: UploadFile = File(...), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in PUBLISH_ROLES:
        raise HTTPException(403, "Your role can review Data Hub history but cannot publish source revisions.")
    spec = _spec(dataset_key)
    payload = await file.read(MAX_DURABLE_UPLOAD_BYTES + 1)
    wrapped = _wrapped(payload, file, str(spec["label"]))
    try:
        inspection = inspect_uploaded_dataset(wrapped, str(spec["label"]))
        inspection.pop("preview", None)
        row = DataHubRepository(engine).publish_source(organization_id=context.organization_id, facility_id=context.facility_id, dataset_key=dataset_key, dataset_label=str(spec["label"]), cache_key=str(spec["cache_key"]), filename=wrapped.name, fingerprint=sha256(payload).hexdigest(), payload=payload, inspection=inspection, content_type=file.content_type or "", imported_by_user_id=context.user_id, imported_by=context.user_id)
        return _history(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/datasets/inspect")
async def inspect_dataset(dataset_key: str = Form(...), file: UploadFile = File(...), context: RequestContext = Depends(get_request_context)):
    if context.role.casefold() not in PUBLISH_ROLES:
        raise HTTPException(403, "Your role can review Data Hub history but cannot publish source revisions.")
    spec = _spec(dataset_key)
    wrapped = _wrapped(await file.read(MAX_DURABLE_UPLOAD_BYTES + 1), file, str(spec["label"]))
    try:
        inspection = inspect_uploaded_dataset(wrapped, str(spec["label"]))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    preview = json.loads(inspection["preview"].to_json(orient="records", date_format="iso"))
    columns = [str(column) for column in inspection["preview"].columns]
    return {
        "dataset_key": dataset_key,
        "dataset_label": str(spec["label"]),
        "name": inspection["name"],
        "rows": inspection["rows"],
        "columns": inspection["columns"],
        "quality": inspection["quality"],
        "matches": inspection["matches"],
        "missing": inspection["missing"],
        "requirements": list(DATASET_REQUIREMENTS.get(str(spec["label"]), {}).keys()),
        "source_columns": columns,
        "preview": preview,
    }


@router.post("/datasets/publish", status_code=201)
async def publish_reviewed_dataset(dataset_key: str = Form(...), mapping_json: str = Form(...), file: UploadFile = File(...), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in PUBLISH_ROLES:
        raise HTTPException(403, "Your role can review Data Hub history but cannot publish source revisions.")
    spec = _spec(dataset_key)
    wrapped = _wrapped(await file.read(MAX_DURABLE_UPLOAD_BYTES + 1), file, str(spec["label"]))
    try:
        mapping = json.loads(mapping_json)
        if not isinstance(mapping, dict):
            raise ValueError("Confirmed column mapping must be an object.")
        inspection = inspect_uploaded_dataset(wrapped, str(spec["label"]))
        source_columns = [str(column) for column in inspection["preview"].columns]
        mapped = build_mapped_upload(wrapped, str(spec["label"]), {str(key): str(value) for key, value in mapping.items()})
        mapped_payload = mapped.getvalue()
        inspection["matches"] = {str(key): str(value) for key, value in mapping.items()}
        inspection["missing"] = []
        inspection["quality"] = "Ready"
        inspection.pop("preview", None)
        row = DataHubRepository(engine).publish_source(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            dataset_key=dataset_key,
            dataset_label=str(spec["label"]),
            cache_key=str(spec["cache_key"]),
            filename=str(mapped.name),
            fingerprint=sha256(mapped_payload).hexdigest(),
            payload=mapped_payload,
            inspection=inspection,
            content_type=str(mapped.type),
            imported_by_user_id=context.user_id,
            imported_by=context.user_id,
        )
        record_approved_mappings(
            engine=engine,
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            dataset_type=str(spec["label"]),
            source_vendor=str(spec["label"]),
            columns=source_columns,
            mappings={str(key): str(value) for key, value in mapping.items()},
        )
        return _history(row)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/datasets/mapping-suggestions")
def mapping_suggestions(
    payload: MappingSuggestionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in PUBLISH_ROLES:
        raise HTTPException(403, "Your role can review Data Hub history but cannot map source revisions.")
    spec = _spec(payload.dataset_key)
    runtime, _access, _org, _facility, _status = build_runtime(engine=engine, settings=settings, context=context, operation_type="retail")
    return suggest_column_mapping(
        payload.columns,
        DATASET_REQUIREMENTS.get(str(spec["label"]), {}),
        existing_matches=payload.existing_matches,
        dataset_label=str(spec["label"]),
        engine=engine,
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        source_vendor=payload.source_vendor.strip() or str(spec["label"]),
        provider_router=runtime.provider_router,
    )


@router.post("/archive")
def archive(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role not in {"dev", "admin", "supervisor"}:
        raise HTTPException(403, "Your role cannot archive Data Hub sources.")
    return {"archived": DataHubRepository(engine).archive_active_sources(context.organization_id, context.facility_id)}
