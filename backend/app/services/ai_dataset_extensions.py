from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import pandas as pd
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.data_hub_repository import DataHubRepository
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.models import TraceabilityStatusEvent, TraceabilityTransactionAttempt
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
        review = safe["review_status"].fillna("").astype(str).str.strip().str.casefold().str.replace("_", "-", regex=False)
        safe = safe.loc[review.ne("demo-only")]
        return safe.reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=COMPLIANCE_COLUMNS)


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
            description="Facility-scoped Metrc/BioTrack transaction counts, in-flight workload and reconciliation burden",
            loader=lambda access: pd.DataFrame([
                traceability.summary(context.organization_id, context.facility_id)
            ]),
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
            freshness="live provider-neutral traceability ledger",
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
