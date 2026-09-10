from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, Organization
from modules.traceability.global_ledger import (
    GlobalTraceabilityLedger,
    classify_failure,
    classify_reconciliation,
    machine_status,
)
from modules.traceability.models import TraceabilityStatusEvent, TraceabilityTransaction, TraceabilityTransactionAttempt


def _ledger():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityTransactionAttempt.__table__.create(engine)
    TraceabilityStatusEvent.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add_all([
            Organization(id="org-1", name="One", slug="one"),
            Organization(id="org-2", name="Two", slug="two"),
            Facility(id="fac-1", organization_id="org-1", name="One", code="ONE"),
            Facility(id="fac-2", organization_id="org-2", name="Two", code="TWO"),
        ])
    return engine, GlobalTraceabilityLedger(engine)


def test_successful_inbound_sync_is_idempotent_and_auditable():
    _engine, ledger = _ledger()
    first = ledger.record_inbound_sync(
        organization_id="org-1", facility_id="fac-1", environment="sandbox",
        license_number="LIC-1", resource="packages", correlation_id="run-1",
        actor="user-1", record_count=2, provider_summary={"persisted": True},
    )
    second = ledger.record_inbound_sync(
        organization_id="org-1", facility_id="fac-1", environment="sandbox",
        license_number="LIC-1", resource="packages", correlation_id="run-1",
        actor="user-1", record_count=2, provider_summary={"persisted": True},
    )
    assert second.id == first.id
    assert machine_status(second) == "succeeded"
    assert second.direction == "inbound"
    assert second.reconciliation_state == "healthy"
    assert len(ledger.list_status_events("org-1", "fac-1", first.id)) == 5


def test_rate_limit_failure_is_retryable_but_validation_is_permanent():
    assert classify_failure(http_status=429).retryable is True
    assert classify_failure(http_status=429).code == "rate_limited"
    assert classify_failure(http_status=422, message="invalid tag").retryable is False
    assert classify_failure(http_status=422, message="invalid tag").code == "provider_validation_rejection"


def test_reconciliation_classifies_missing_mismatch_relationship_and_stale():
    assert classify_reconciliation({}, {"id": 1}).state == "missing_locally"
    assert classify_reconciliation({"id": 1}, {}).state == "missing_remotely"
    assert classify_reconciliation({"id": 1}, {"id": 2}).state == "field_mismatch"
    assert classify_reconciliation({"source": 1}, {"source": 2}, relationship_fields=("source",)).state == "relationship_mismatch"
    assert classify_reconciliation({"id": 1}, {"id": 1}, stale=True).state == "stale_data"
    assert classify_reconciliation({"id": 1}, {"id": 1}).state == "healthy"


def test_exception_queries_isolate_org_facility_and_environment():
    _engine, ledger = _ledger()
    failed = ledger.record_inbound_failure(
        organization_id="org-1", facility_id="fac-1", environment="sandbox",
        license_number="LIC-1", resource="packages", correlation_id="run-fail",
        actor="user-1", http_status=429, error_code="rate_limit", message="Too many requests",
    )
    assert [row.id for row in ledger.list_exceptions("org-1", "fac-1", environment="sandbox")] == [failed.id]
    assert ledger.list_exceptions("org-1", "fac-1", environment="production") == []
    assert ledger.list_exceptions("org-2", "fac-2") == []


def test_retry_preserves_idempotency_and_is_bounded():
    engine, ledger = _ledger()
    failed = ledger.record_inbound_failure(
        organization_id="org-1", facility_id="fac-1", environment="sandbox",
        license_number="LIC-1", resource="packages", correlation_id="retry-1",
        actor="user-1", http_status=503, error_code="temporary", message="Provider unavailable",
    )
    key = failed.idempotency_key
    queued = ledger.prepare_retry("org-1", "fac-1", failed.id, actor="supervisor", reason="Provider recovered; retry same request.")
    assert queued.status == "queued"
    assert queued.idempotency_key == key
    assert queued.resolution_state == "in_progress"
    with sessionmaker(bind=engine, expire_on_commit=False, future=True).begin() as session:
        row = session.get(TraceabilityTransaction, failed.id)
        row.status = "rejected"
        row.retry_eligible = True
        row.attempt_count = 4
    try:
        ledger.prepare_retry("org-1", "fac-1", failed.id, actor="supervisor", reason="retry")
        assert False, "bounded retry must reject the fifth attempt"
    except ValueError as exc:
        assert "cannot be retried safely" in str(exc)


def test_entity_history_links_direct_and_parent_entities_and_resolution():
    _engine, ledger = _ledger()
    row = ledger.create_transaction(
        organization_id="org-1", facility_id="fac-1", provider="metrc",
        operation_type="package_create", entity_type="package", entity_id="pkg-1",
        parent_entity_type="harvest", parent_entity_id="harvest-1",
        related_entities=[{"type": "plant", "id": "plant-1"}],
        idempotency_key="outbound-1", actor="user-1", environment="production",
    )
    assert [event.id for event in ledger.entity_history("org-1", "fac-1", "package", "pkg-1")] == [row.id]
    assert [event.id for event in ledger.entity_history("org-1", "fac-1", "harvest", "harvest-1")] == [row.id]
    ledger.transition_logged(
        organization_id="org-1", facility_id="fac-1", transaction_id=row.id,
        new_status="rejected", actor="provider", reason="Invalid tag", source="provider",
    )
    resolved = ledger.resolve_exception("org-1", "fac-1", row.id, actor="qa-1", note="Corrected tag mapping in Product 360.")
    assert resolved.resolution_state == "resolved"
    assert machine_status(resolved) == "resolved"
    assert ledger.list_exceptions("org-1", "fac-1") == []
