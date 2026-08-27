from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine

from backend.app.auth import RequestContext
from backend.app.services import ai_dataset_extensions as extensions
from services.ai.datasets import DatasetAccessContext, DatasetRegistry


def _context() -> RequestContext:
    return RequestContext(
        user_id="user-a",
        organization_id="org-a",
        facility_id="fac-a",
        role="qa",
    )


def test_governed_agent_datasets_register_without_loading_database_rows():
    registry = DatasetRegistry()
    engine = create_engine("sqlite+pysqlite:///:memory:")

    extensions.register_governed_agent_datasets(registry, _context(), engine)

    assert {
        "compliance_sources",
        "traceability_summary",
        "traceability_transactions",
        "traceability_reconciliation_queue",
        "traceability_attempts",
        "traceability_status_events",
    }.issubset(set(registry.keys()))

    access = DatasetAccessContext(
        "org-a",
        "fac-a",
        "user-a",
        "qa",
        frozenset({"retail"}),
        operation_type="retail",
        engine=engine,
    )
    compliance_keys = {row["key"] for row in registry.describe("compliance", access)}
    assert "compliance_sources" in compliance_keys
    assert "traceability_transactions" in compliance_keys
    assert "traceability_reconciliation_queue" in compliance_keys


def test_compliance_dataset_uses_structured_allowlist_and_excludes_demo_only(monkeypatch):
    csv_payload = b"state,scope,topic,answer,source_citation,source_url,last_updated,review_status,api_key\nMA,adult-use,labels,Reviewed answer,935 CMR 500,https://mass.gov,2026-08-01,reviewed,secret-a\nCA,adult-use,packaging,Demo answer,Demo citation,https://example.test,2026-08-01,demo-only,secret-b\n"
    source = SimpleNamespace(
        dataset_key="compliance_sources",
        filename="compliance.csv",
        payload=csv_payload,
    )

    class FakeDataHubRepository:
        def __init__(self, _engine):
            pass

        def list_active_sources(self, organization_id, facility_id):
            assert organization_id == "org-a"
            assert facility_id == "fac-a"
            return [source]

    monkeypatch.setattr(extensions, "DataHubRepository", FakeDataHubRepository)

    frame = extensions._compliance_source_rows(object(), _context())

    assert list(frame.columns) == list(extensions.COMPLIANCE_COLUMNS)
    assert len(frame) == 1
    assert frame.iloc[0]["state"] == "MA"
    assert frame.iloc[0]["review_status"] == "reviewed"
    assert "api_key" not in frame.columns
    assert "Demo answer" not in frame["answer"].tolist()


def test_traceability_agent_specs_never_expose_payloads_or_user_identity():
    registry = DatasetRegistry()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    extensions.register_governed_agent_datasets(registry, _context(), engine)

    forbidden = {
        "request_payload_json",
        "response_payload_json",
        "idempotency_key",
        "requested_by",
        "approved_by",
        "actor",
        "error_message",
    }
    for key in (
        "traceability_transactions",
        "traceability_reconciliation_queue",
        "traceability_attempts",
        "traceability_status_events",
    ):
        spec = registry._specs[key]
        assert forbidden.isdisjoint(set(spec.allowed_columns))

    tx_columns = set(registry._specs["traceability_transactions"].allowed_columns)
    assert {"provider", "operation_type", "entity_type", "status", "error_code", "attempt_count"}.issubset(tx_columns)
