from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.data_hub_repository import DataHubRepository
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.models import (
    TRACEABILITY_STATUSES,
    TraceabilityStatusEvent,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)
from services.ai.datasets import DatasetRegistry, DatasetSpec, objects_frame

from ..auth import RequestContext


COMPLIANCE_SOURCE_KEYS = ("compliance_sources", "sandbox_compliance_sources")
COMPLIANCE_COLUMNS = (
    "state",
    "scope",
    "topic",
    "answer",
    "source_citation",
    "source_url",
    "last_updated",
    "review_status",
)
APPROVED_REVIEW_STATUSES = frozenset({"reviewed", "approved", "verified", "current"})
TRACEABILITY_AGENTS = (
    "ops",
    "buyer",
    "purchasing",
    "inventory",
    "audit",
    "compliance",
    "nomenclature",
    "repack",
    "coman",
    "extraction",
    "commercial",
    "cultivation",
    "data_hub",
)
TRACEABILITY_TRANSACTION_COLUMNS = (
    "id",
    "provider",
    "operation_type",
    "entity_type",
    "entity_id",
    "status",
    "external_reference",
    "error_code",
    "attempt_count",
    "next_attempt_at",
    "requested_at",
    "submitted_at",
    "completed_at",
)


def _frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if value is None:
        return pd.DataFrame()
    if isinstance(value, list):
        return objects_frame(value) if value and not isinstance(value[0], dict) else pd.DataFrame(value)
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return objects_frame([value])


def _normalized_column(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def _review_status(value: object) -> str:
    return str(value or "").strip().casefold().replace("_", "-")


def _compliance_source_rows(engine: Engine, context: RequestContext) -> pd.DataFrame:
    """Load only the structured compliance fields already accepted by Compliance Q&A.

    Synthetic demo-only rows are intentionally excluded so the general Agent runtime
    cannot promote them into regulatory claims. The file bytes and any extra uploaded
    columns never enter model-visible context.
    """

    try:
        repository = DataHubRepository(engine)
        active = {
            source.dataset_key: source
            for source in repository.list_active_sources(context.organization_id, context.facility_id)
        }
        source = next((active[key] for key in COMPLIANCE_SOURCE_KEYS if key in active), None)
        if source is None:
            return pd.DataFrame(columns=COMPLIANCE_COLUMNS)

        filename = str(source.filename or "").casefold()
        payload = bytes(source.payload or b"")
        if filename.endswith(".csv"):
            frame = pd.read_csv(BytesIO(payload))
        elif filename.endswith((".xlsx", ".xls")):
            frame = pd.read_excel(BytesIO(payload))
        else:
            return pd.DataFrame(columns=COMPLIANCE_COLUMNS)

        frame = frame.rename(columns={column: _normalized_column(column) for column in frame.columns})
        if any(column not in frame.columns for column in COMPLIANCE_COLUMNS):
            return pd.DataFrame(columns=COMPLIANCE_COLUMNS)

        safe = frame.loc[:, list(COMPLIANCE_COLUMNS)].copy()
        review = safe["review_status"].fillna("").map(_review_status)
        safe = safe.loc[review.ne("demo-only")]
        return safe.reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=COMPLIANCE_COLUMNS)


def _structured_compliance_results(
    engine: Engine,
    context: RequestContext,
    query: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Convert approved structured Compliance Q&A rows into level-two evidence.

    These rows can satisfy the compliance profile's approved-source gate, but they
    deliberately remain authority level 2. Explicit legal/regulatory conclusions
    still require authority-level-1 government/regulatory evidence from KnowledgeStore.
    """

    frame = _compliance_source_rows(engine, context)
    if frame.empty:
        return []

    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", str(query or "").casefold())
        if len(token) >= 3
    }
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for position, row in enumerate(frame.to_dict("records")):
        review_status = _review_status(row.get("review_status"))
        if review_status not in APPROVED_REVIEW_STATUSES:
            continue
        required = (
            row.get("state"),
            row.get("scope"),
            row.get("answer"),
            row.get("source_citation"),
            row.get("source_url"),
            row.get("last_updated"),
        )
        if any(not str(value or "").strip() for value in required):
            continue
        searchable = " ".join(
            str(row.get(key) or "").casefold()
            for key in ("state", "scope", "topic", "answer", "source_citation")
        )
        score = sum(1 for token in query_tokens if token in searchable)
        result = {
            "title": f"{row.get('state')} {row.get('scope')} {row.get('topic')}",
            "source": "compliance_q&a_data_hub",
            "source_type": "approved_structured_compliance",
            "authority_level": 2,
            "jurisdiction": str(row.get("state") or ""),
            "effective_date": str(row.get("last_updated") or ""),
            "updated_at": str(row.get("last_updated") or ""),
            "version": review_status,
            "url": str(row.get("source_url") or ""),
            "page_or_section": str(row.get("source_citation") or ""),
            "content": str(row.get("answer") or ""),
            "score": float(score),
        }
        ranked.append((score, position, result))

    if not ranked:
        return []
    if any(score > 0 for score, _position, _result in ranked):
        ranked = [item for item in ranked if item[0] > 0]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    safe_limit = max(1, min(int(limit or 8), 20))
    return [result for _score, _position, result in ranked[:safe_limit]]


class GovernedKnowledgeRetriever:
    """Blend approved structured compliance rows into the native retrieval layer."""

    def __init__(self, base_retriever: Any, engine: Engine, context: RequestContext):
        self.base_retriever = base_retriever
        self.engine = engine
        self.context = context

    def search(self, *, scope: Any, query: str, limit: int = 8, authoritative_only: bool = False) -> dict[str, Any]:
        base = self.base_retriever.search(
            scope=scope,
            query=query,
            limit=limit,
            authoritative_only=authoritative_only,
        )
        results = list(base.get("results") or [])
        if (
            str(getattr(scope, "organization_id", "")) == self.context.organization_id
            and str(getattr(scope, "facility_id", "")) == self.context.facility_id
        ):
            structured = _structured_compliance_results(
                self.engine,
                self.context,
                query,
                limit=max(1, int(limit or 8)),
            )
            seen = {
                (str(row.get("title") or ""), str(row.get("url") or ""), str(row.get("page_or_section") or ""))
                for row in results
            }
            for row in structured:
                key = (str(row.get("title") or ""), str(row.get("url") or ""), str(row.get("page_or_section") or ""))
                if key not in seen:
                    results.append(row)
                    seen.add(key)
        return {
            **base,
            "results": results[: max(1, int(limit or 8))],
            "retrieval_mode": "knowledge+structured_compliance" if results else str(base.get("retrieval_mode") or "unavailable"),
        }


def _traceability_summary(engine: Engine, context: RequestContext) -> pd.DataFrame:
    """Aggregate the complete facility ledger instead of a recent-row window."""

    with Session(engine) as session:
        rows = session.execute(
            select(TraceabilityTransaction.status, func.count(TraceabilityTransaction.id))
            .where(
                TraceabilityTransaction.organization_id == context.organization_id,
                TraceabilityTransaction.facility_id == context.facility_id,
            )
            .group_by(TraceabilityTransaction.status)
        ).all()
    counts = {status: 0 for status in TRACEABILITY_STATUSES}
    for status, count in rows:
        normalized = str(status or "").strip().casefold()
        if normalized in counts:
            counts[normalized] = int(count or 0)
    counts["total"] = sum(counts[status] for status in TRACEABILITY_STATUSES)
    counts["needs_reconciliation"] = counts["rejected"] + counts["reconciliation_required"]
    counts["in_flight"] = sum(
        counts[status]
        for status in ("requested", "validated", "queued", "submitted", "accepted")
    )
    return pd.DataFrame([counts])


def register_governed_agent_datasets(
    registry: DatasetRegistry,
    context: RequestContext,
    engine: Engine,
) -> None:
    """Register regulated-source and state-traceability datasets for native Agents."""

    registry.register(
        DatasetSpec(
            key="compliance_sources",
            domain="compliance",
            description="Facility-authorized structured compliance source rows with citations and review state",
            loader=lambda access: _compliance_source_rows(engine, context),
            allowed_agents=TRACEABILITY_AGENTS,
            allowed_columns=COMPLIANCE_COLUMNS,
            freshness="active Compliance Q&A Data Hub source",
            max_tool_rows=50,
        )
    )

    traceability = TraceabilityBackofficeRepository(engine)

    registry.register(
        DatasetSpec(
            key="traceability_summary",
            domain="traceability",
            description="Complete facility-scoped Metrc/BioTrack transaction counts, in-flight workload and reconciliation burden",
            loader=lambda access: _traceability_summary(engine, context),
            allowed_agents=TRACEABILITY_AGENTS,
            allowed_columns=(
                "total",
                "requested",
                "validated",
                "queued",
                "submitted",
                "accepted",
                "rejected",
                "verified",
                "reconciliation_required",
                "cancelled",
                "needs_reconciliation",
                "in_flight",
            ),
            freshness="live full provider-neutral traceability ledger",
            max_tool_rows=5,
        )
    )

    registry.register(
        DatasetSpec(
            key="traceability_transactions",
            domain="traceability",
            description="Safe facility-scoped state traceability action lifecycle without request/response payloads or user identity",
            loader=lambda access: _frame(
                traceability.list_transactions(context.organization_id, context.facility_id, limit=500)
            ),
            allowed_agents=TRACEABILITY_AGENTS,
            allowed_columns=TRACEABILITY_TRANSACTION_COLUMNS,
            sensitive_columns=(
                "license_number",
                "idempotency_key",
                "request_payload_json",
                "response_payload_json",
                "requested_by",
                "approved_by",
                "reason",
                "error_message",
                "actor",
            ),
            freshness="live provider-neutral traceability ledger",
            max_tool_rows=50,
        )
    )

    registry.register(
        DatasetSpec(
            key="traceability_reconciliation_queue",
            domain="traceability",
            description="Rejected or reconciliation-required Metrc/BioTrack actions needing operational attention",
            loader=lambda access: _frame(
                traceability.list_reconciliation_queue(context.organization_id, context.facility_id)[:500]
            ),
            allowed_agents=TRACEABILITY_AGENTS,
            allowed_columns=TRACEABILITY_TRANSACTION_COLUMNS,
            sensitive_columns=(
                "license_number",
                "idempotency_key",
                "request_payload_json",
                "response_payload_json",
                "requested_by",
                "approved_by",
                "reason",
                "error_message",
                "actor",
            ),
            freshness="live provider-neutral traceability reconciliation queue",
            max_tool_rows=50,
        )
    )

    def attempt_rows(_access) -> pd.DataFrame:
        with Session(engine) as session:
            rows = list(
                session.scalars(
                    select(TraceabilityTransactionAttempt)
                    .where(
                        TraceabilityTransactionAttempt.organization_id == context.organization_id,
                        TraceabilityTransactionAttempt.facility_id == context.facility_id,
                    )
                    .order_by(TraceabilityTransactionAttempt.started_at.desc())
                    .limit(500)
                )
            )
        return _frame(rows)

    registry.register(
        DatasetSpec(
            key="traceability_attempts",
            domain="traceability",
            description="Safe provider-call attempt telemetry for state traceability actions",
            loader=attempt_rows,
            allowed_agents=TRACEABILITY_AGENTS,
            allowed_columns=(
                "id",
                "transaction_id",
                "attempt_number",
                "http_status",
                "error_code",
                "started_at",
                "completed_at",
            ),
            sensitive_columns=(
                "request_payload_json",
                "response_payload_json",
                "error_message",
            ),
            freshness="live provider-neutral traceability attempt ledger",
            max_tool_rows=50,
        )
    )

    def status_event_rows(_access) -> pd.DataFrame:
        with Session(engine) as session:
            rows = list(
                session.scalars(
                    select(TraceabilityStatusEvent)
                    .where(
                        TraceabilityStatusEvent.organization_id == context.organization_id,
                        TraceabilityStatusEvent.facility_id == context.facility_id,
                    )
                    .order_by(TraceabilityStatusEvent.occurred_at.desc())
                    .limit(500)
                )
            )
        return _frame(rows)

    registry.register(
        DatasetSpec(
            key="traceability_status_events",
            domain="traceability",
            description="Append-only state traceability lifecycle transitions without employee identity or free-text reasons",
            loader=status_event_rows,
            allowed_agents=TRACEABILITY_AGENTS,
            allowed_columns=(
                "id",
                "transaction_id",
                "from_status",
                "to_status",
                "source",
                "occurred_at",
            ),
            sensitive_columns=("actor", "reason"),
            freshness="live append-only traceability status history",
            max_tool_rows=50,
        )
    )
