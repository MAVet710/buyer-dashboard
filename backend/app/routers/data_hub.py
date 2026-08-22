from hashlib import sha256
from io import BytesIO
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import Engine

from modules.data_hub_core import RETAIL_DATASETS, inspect_uploaded_dataset
from modules.data_hub_repository import DataHubRepository, MAX_DURABLE_UPLOAD_BYTES
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/data-hub", tags=["data-hub"])
SPECS = {str(spec["dataset_key"]): spec for spec in RETAIL_DATASETS}
PUBLISH_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "trial"}


def _history(row):
    return {key: getattr(row, key) for key in ("id", "dataset_key", "dataset_label", "filename", "content_type", "fingerprint", "payload_size", "row_count", "column_count", "quality", "status", "imported_by", "activated_at", "created_at") } | {"mapping": json.loads(row.mapping_json or "{}"), "missing_fields": json.loads(row.missing_fields_json or "[]")}


@router.get("/datasets")
def datasets(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    history = DataHubRepository(engine).list_history(context.organization_id, context.facility_id)
    return {"catalog": [{key: spec[key] for key in ("label", "dataset_key", "description", "types")} for spec in RETAIL_DATASETS], "history": [_history(row) for row in history]}


@router.post("/datasets", status_code=201)
async def upload_dataset(dataset_key: str = Form(...), file: UploadFile = File(...), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in PUBLISH_ROLES:
        raise HTTPException(403, "Your role can review Data Hub history but cannot publish source revisions.")
    spec = SPECS.get(dataset_key)
    if not spec: raise HTTPException(422, "Unsupported Data Hub dataset.")
    payload = await file.read(MAX_DURABLE_UPLOAD_BYTES + 1)
    if not payload: raise HTTPException(422, "The source file is empty.")
    if len(payload) > MAX_DURABLE_UPLOAD_BYTES: raise HTTPException(413, "The source file exceeds the 10 MB durable upload limit.")
    wrapped = BytesIO(payload); wrapped.name = file.filename or str(spec["label"]); wrapped.type = file.content_type or ""
    try:
        inspection = inspect_uploaded_dataset(wrapped, str(spec["label"]))
        inspection.pop("preview", None)
        row = DataHubRepository(engine).publish_source(organization_id=context.organization_id, facility_id=context.facility_id, dataset_key=dataset_key, dataset_label=str(spec["label"]), cache_key=str(spec["cache_key"]), filename=wrapped.name, fingerprint=sha256(payload).hexdigest(), payload=payload, inspection=inspection, content_type=file.content_type or "", imported_by_user_id=context.user_id, imported_by=context.user_id)
        return _history(row)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/archive")
def archive(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role not in {"dev", "admin", "supervisor"}: raise HTTPException(403, "Your role cannot archive Data Hub sources.")
    return {"archived": DataHubRepository(engine).archive_active_sources(context.organization_id, context.facility_id)}
