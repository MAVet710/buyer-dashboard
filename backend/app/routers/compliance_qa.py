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
from modules.integrations import IntegrationConfigurationService
from services.doobie_client import DoobieClient
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/compliance-qa", tags=["compliance-qa"])

SOURCE_KEYS = ("compliance_sources", "sandbox_compliance_sources")
REQUIRED = ("state", "scope", "topic", "answer", "source_citation", "source_url", "last_updated", "review_status")
WRITE_ROLES = {"dev", "admin", "buyer", "qa", "supervisor"}
DEFAULT_QUESTION = "What are the packaging requirements for adult-use products?"


class ComplianceQuery(BaseModel):
    question: str = Field(default=DEFAULT_QUESTION, max_length=2000)
    state: str = Field(default="CA", max_length=64)
    scope: str = Field(default="adult-use", max_length=64)
    topic: str = Field(default="packaging", max_length=240)


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def _read(payload: bytes, filename: str) -> pd.DataFrame:
    suffix = filename.casefold()
    if suffix.endswith(".csv"):
        frame = pd.read_csv(BytesIO(payload))
    elif suffix.endswith((".xlsx", ".xls")):
        # Data Hub may already contain an older Excel source. The exact
        # Streamlit Compliance Q&A uploader remains CSV-only in the web UI.
        frame = pd.read_excel(BytesIO(payload))
    else:
        raise ValueError("Use a CSV compliance source file.")
    frame = frame.rename(columns={column: _norm(column) for column in frame.columns})
    missing = [column for column in REQUIRED if column not in frame.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
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
                scope=str(row.get("scope") or "").strip().lower(),
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


def _preview(frame: pd.DataFrame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in frame.head(100).to_dict("records"):
        clean: dict[str, str] = {}
        for key, value in row.items():
            if pd.isna(value):
                clean[str(key)] = ""
            elif hasattr(value, "isoformat"):
                clean[str(key)] = str(value.isoformat())
            else:
                clean[str(key)] = str(value)
        rows.append(clean)
    return rows


def _platform_doobie(engine: Engine, settings: Settings) -> DoobieClient | None:
    """Resolve Doobie without making it a dependency of deterministic compliance retrieval."""
    try:
        service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
        row = service.get("platform", "global", "doobie")
        if row is None:
            return None
        configuration = service.public(row).get("configuration") or {}
        base_url = str(configuration.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            return None
        return DoobieClient(base_url=base_url, api_key=service.secret(row), timeout_seconds=12)
    except (RuntimeError, ValueError, TypeError):
        return None


def _grounded_answer(
    *,
    matches: list[ComplianceSource],
    question: str,
    state: str,
    scope: str,
    topic: str,
    engine: Engine,
    settings: Settings,
) -> str:
    base_answer = format_compliance_answer(matches)
    if not matches:
        return base_answer

    client = _platform_doobie(engine, settings)
    if client is None:
        return base_answer

    context = "\n\n".join(
        (
            f"State: {item.state}\n"
            f"Scope: {item.scope}\n"
            f"Topic: {item.topic}\n"
            f"Answer: {item.answer}\n"
            f"Citation: {item.source_citation}\n"
            f"URL: {item.source_url}\n"
            f"Last Updated: {item.last_updated.isoformat()}\n"
            f"Review Status: {item.review_status}"
        )
        for item in matches
    )
    prompt = (
        "Use only the provided source rows to answer the compliance question.\n"
        "Do not invent regulations.\n\n"
        f"Question: {question}\n"
        f"State: {state}\n"
        f"Scope: {scope}\n"
        f"Topic: {topic}\n\n"
        f"Sources:\n{context}\n\n"
        "Output format:\n"
        "- Short answer\n"
        "- Bullet list of source-backed requirements\n"
        "- Include citation tags exactly as written in source rows\n"
        "- Include source URLs\n"
        "- Include last updated date and review status"
    )
    response = client.copilot(
        question=prompt,
        data={"source_rows": [_payload(item) for item in matches]},
        persona="compliance",
        state=state,
        department="compliance",
    )
    if response.get("mode") == "fallback":
        return base_answer
    synthesized = str(response.get("answer") or "").strip()
    if not synthesized:
        return base_answer
    return f"{synthesized}\n\n---\n\nSource Records\n\n{base_answer}"


@router.get("/status")
def status(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    source = _source(DataHubRepository(engine), context.organization_id, context.facility_id)
    if source is None:
        return {"configured": False, "rows": 0, "filename": "", "topics": [], "columns": list(REQUIRED), "preview": []}
    try:
        frame = _read(source.payload, source.filename)
    except ValueError as exc:
        return {
            "configured": False,
            "rows": source.row_count,
            "filename": source.filename,
            "topics": [],
            "columns": list(REQUIRED),
            "preview": [],
            "error": str(exc),
        }
    return {
        "configured": True,
        "rows": len(frame),
        "filename": source.filename,
        "quality": source.quality,
        "topics": sorted({str(value) for value in frame["topic"].dropna() if str(value).strip()}),
        "columns": [str(column) for column in frame.columns],
        "preview": _preview(frame),
    }


@router.get("/template")
def template(_context: RequestContext = Depends(get_request_context)):
    template_frame = pd.DataFrame(
        [
            {
                "state": "CA",
                "scope": "adult-use",
                "topic": "packaging",
                "answer": "Child-resistant packaging is required before retail sale.",
                "source_citation": "16 CCR § 17407",
                "source_url": "https://cannabis.ca.gov/",
                "last_updated": "2026-01-15",
                "review_status": "reviewed",
            }
        ]
    )
    return Response(
        content=template_frame.to_csv(index=False).encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="compliance_sources_template.csv"'},
    )


@router.post("/sources", status_code=201)
async def upload_source(
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role cannot upload compliance sources.")
    filename = file.filename or "compliance_sources.csv"
    if not filename.casefold().endswith(".csv"):
        raise HTTPException(422, "Use a CSV compliance source file.")
    payload = await file.read(MAX_DURABLE_UPLOAD_BYTES + 1)
    if not payload:
        raise HTTPException(422, "The source file is empty.")
    if len(payload) > MAX_DURABLE_UPLOAD_BYTES:
        raise HTTPException(413, "Compliance source files must be 10 MB or smaller.")
    try:
        frame = _read(payload, filename)
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
        filename=filename,
        fingerprint=sha256(payload).hexdigest(),
        payload=payload,
        content_type=file.content_type or "text/csv",
        inspection={
            "rows": len(frame),
            "columns": len(frame.columns),
            "quality": quality,
            "matches": {column: column for column in REQUIRED},
            "missing": [],
        },
        imported_by_user_id=context.user_id,
        imported_by=context.user_id,
    )
    return {"id": row.id, "filename": row.filename, "rows": row.row_count, "quality": row.quality, "preview": _preview(frame)}


@router.post("/query")
def query(
    payload: ComplianceQuery,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    source = _source(DataHubRepository(engine), context.organization_id, context.facility_id)
    if source is None:
        raise HTTPException(422, "Upload structured compliance source rows first.")
    try:
        records = _records(_read(source.payload, source.filename))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    repository = ComplianceRepository(records)
    matches = repository.query(
        state=payload.state,
        scope=payload.scope,
        topic=payload.topic,
    )
    answer = _grounded_answer(
        matches=matches,
        question=payload.question,
        state=payload.state,
        scope=payload.scope,
        topic=payload.topic,
        engine=engine,
        settings=settings,
    )
    return {
        "answer": answer,
        "sources": [_payload(row) for row in matches],
        "source_file": source.filename,
        "grounded": bool(matches),
    }
