from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
import re

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from compliance_engine import ComplianceRepository, ComplianceSource, format_compliance_answer
from modules.data_hub_repository import DataHubRepository, MAX_DURABLE_UPLOAD_BYTES
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/compliance-qa", tags=["compliance-qa"])

SOURCE_KEYS = ("compliance_sources", "sandbox_compliance_sources")
REQUIRED = ("state", "scope", "topic", "answer", "source_citation", "source_url", "last_updated", "review_status")
WRITE_ROLES = {"dev", "admin", "qa", "supervisor"}


class ComplianceQuery(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    state: str = Field(default="MA", max_length=64)
    scope: str = Field(default="adult-use", max_length=64)


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def _read(payload: bytes, filename: str) -> pd.DataFrame:
    suffix = filename.casefold()
    if suffix.endswith(".csv"):
        frame = pd.read_csv(BytesIO(payload))
    elif suffix.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(BytesIO(payload))
    else:
        raise ValueError("Use a CSV, XLSX, or XLS compliance source file.")
    frame = frame.rename(columns={column: _norm(column) for column in frame.columns})
    missing = [column for column in REQUIRED if column not in frame.columns]
    if missing:
        raise ValueError("Compliance source is missing: " + ", ".join(missing))
    if frame.empty:
        raise ValueError("Compliance source contains no rows.")
    return frame


def _source(repository: DataHubRepository, organization_id: str, facility_id: str):
    active = {source.dataset_key: source for source in repository.list_active_sources(organization_id, facility_id)}
    for key in SOURCE_KEYS:
        if key in active:
            return active[key]
    return None


def _records(frame: pd.DataFrame) -> list[ComplianceSource]:
    records: list[ComplianceSource] = []
    for row in frame.to_dict("records"):
        parsed = pd.to_datetime(row.get("last_updated"), errors="coerce")
        updated = parsed.date() if pd.notna(parsed) else date.today()
        records.append(
            ComplianceSource(
                state=str(row.get("state") or "").strip(),
                scope=str(row.get("scope") or "").strip(),
                topic=str(row.get("topic") or "").strip(),
                answer=str(row.get("answer") or "").strip(),
                source_citation=str(row.get("source_citation") or "").strip(),
                source_url=str(row.get("source_url") or "").strip(),
                last_updated=updated,
                review_status=str(row.get("review_status") or "").strip(),
            )
        )
    return records


def _payload(row: ComplianceSource) -> dict:
    return {
        "state": row.state,
        "scope": row.scope,
        "topic": row.topic,
        "answer": row.answer,
        "source_citation": row.source_citation,
        "source_url": row.source_url,
        "last_updated": row.last_updated.isoformat(),
        "review_status": row.review_status,
    }


@router.get("/status")
def status(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    source = _source(DataHubRepository(engine), context.organization_id, context.facility_id)
    if source is None:
        return {"configured": False, "rows": 0, "filename": "", "topics": []}
    try:
        frame = _read(source.payload, source.filename)
    except ValueError as exc:
        return {"configured": False, "rows": source.row_count, "filename": source.filename, "topics": [], "error": str(exc)}
    return {
        "configured": True,
        "rows": len(frame),
        "filename": source.filename,
        "quality": source.quality,
        "topics": sorted({str(value) for value in frame["topic"].dropna() if str(value).strip()}),
    }


@router.get("/template")
def template():
    template_frame = pd.DataFrame(
        [
            {
                "state": "MA",
                "scope": "adult-use",
                "topic": "inventory",
                "answer": "Reviewed operational answer goes here.",
                "source_citation": "935 CMR ...",
                "source_url": "https://masscannabiscontrol.com/...",
                "last_updated": date.today().isoformat(),
                "review_status": "reviewed",
            }
        ]
    )
    return Response(
        content=template_frame.to_csv(index=False).encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="Buyer_Dash_Compliance_Source_Template.csv"'},
    )


@router.post("/sources", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role cannot publish compliance sources.")
    payload = await file.read(MAX_DURABLE_UPLOAD_BYTES + 1)
    if not payload:
        raise HTTPException(422, "The source file is empty.")
    if len(payload) > MAX_DURABLE_UPLOAD_BYTES:
        raise HTTPException(413, "Compliance source files must be 10 MB or smaller.")
    try:
        frame = _read(payload, file.filename or "compliance.csv")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    statuses = frame["review_status"].fillna("").astype(str).str.casefold()
    quality = "Ready" if statuses.isin(["reviewed", "approved", "current"]).all() else "Review status required"
    row = DataHubRepository(engine).publish_source(
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        dataset_key="compliance_sources",
        dataset_label="Compliance Sources",
        cache_key="compliance_sources_df",
        filename=file.filename or "compliance.csv",
        fingerprint=sha256(payload).hexdigest(),
        payload=payload,
        content_type=file.content_type or "",
        inspection={"rows": len(frame), "columns": len(frame.columns), "quality": quality, "matches": {column: column for column in REQUIRED}, "missing": []},
        imported_by_user_id=context.user_id,
        imported_by=context.user_id,
    )
    return {"id": row.id, "filename": row.filename, "rows": row.row_count, "quality": row.quality}


@router.post("/query")
def query(payload: ComplianceQuery, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    source = _source(DataHubRepository(engine), context.organization_id, context.facility_id)
    if source is None:
        raise HTTPException(422, "No reviewed compliance source is active for this facility.")
    try:
        records = _records(_read(source.payload, source.filename))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    state = payload.state.strip().casefold()
    scope = payload.scope.strip().casefold()
    question_tokens = {token for token in re.findall(r"[a-z0-9]+", payload.question.casefold()) if len(token) > 2}
    eligible = [
        row for row in records
        if row.state.casefold() == state and row.scope.casefold() in {scope, "both"}
        and row.review_status.casefold() not in {"draft", "stale", "unreviewed"}
    ]
    ranked = sorted(
        eligible,
        key=lambda row: len(question_tokens & set(re.findall(r"[a-z0-9]+", (row.topic + " " + row.answer).casefold()))),
        reverse=True,
    )
    if not ranked:
        return {"answer": format_compliance_answer([]), "sources": [], "source_file": source.filename}
    best_score = len(question_tokens & set(re.findall(r"[a-z0-9]+", (ranked[0].topic + " " + ranked[0].answer).casefold())))
    matches = ranked[:3] if best_score > 0 else []
    return {
        "answer": format_compliance_answer(matches),
        "sources": [_payload(row) for row in matches],
        "source_file": source.filename,
        "grounded": bool(matches),
    }
