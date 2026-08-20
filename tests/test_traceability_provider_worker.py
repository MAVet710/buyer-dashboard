import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.models import (
    TraceabilityStatusEvent,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)
from modules.traceability.processor import (
    TraceabilityCredentials,
    process_transaction,
)


def _repository():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityTransactionAttempt.__table__.create(engine)
    TraceabilityStatusEvent.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1", name="Demo Operator", slug="demo-operator"))
        session.add(
            Facility(
                id="fac-1",
                organization_id="org-1",
                name="Demo Facility",
                code="DEMO",
            )
        )
    return TraceabilityBackofficeRepository(engine)


def _queued_adjustment(repo):
    transaction = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406030000TEST001",
        idempotency_key="adjustment:test:1",
        actor="operator",
        license_number="MR123",
        request_payload={
            "package_label": "1A406030000TEST001",
            "adjustment_type": "incremental",
            "quantity": -2.0,
            "unit": "g",
            "reason": "Scale Variance",
            "reason_note": "Count correction",
            "UserApiKey": "must-never-persist",
        },
    )
    transaction = repo.transition_logged(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="validated",
        actor="operator",
        reason="Validated package and quantity.",
    )
    return repo.transition_logged(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="queued",
        actor="operator",
        reason="Approved for provider submission.",
    )


def _credentials():
    return TraceabilityCredentials(
        provider="metrc",
        state="MA",
        user_api_key="runtime-user-key",
        integrator_api_key="runtime-integrator-key",
        license_number="MR123",
    )


def test_provider_worker_records_successful_attempt_and_accepts_transaction(monkeypatch):
    repo = _repository()
    transaction = _queued_adjustment(repo)
    captured = {}

    def fake_submit(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "status": "connected",
            "http_status": 200,
            "message": "Metrc package adjustment succeeded.",
        }

    monkeypatch.setattr("modules.traceability.processor.submit_package_adjustment", fake_submit)
    result = process_transaction(
        repo,
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        credentials=_credentials(),
        actor="traceability-worker",
    )

    assert result.status == "accepted"
    assert captured["package_label"] == "1A406030000TEST001"
    assert captured["user_api_key"] == "runtime-user-key"
    assert captured["integrator_api_key"] == "runtime-integrator-key"

    attempts = repo.list_attempts("org-1", "fac-1", transaction.id)
    assert len(attempts) == 1
    assert attempts[0].http_status == 200
    stored_request = json.loads(attempts[0].request_payload_json)
    assert stored_request["UserApiKey"] == "[REDACTED]"
    assert "runtime-user-key" not in attempts[0].request_payload_json
    assert "runtime-integrator-key" not in attempts[0].request_payload_json

    events = repo.list_status_events("org-1", "fac-1", transaction.id)
    assert [(event.from_status, event.to_status) for event in events][-2:] == [
        ("queued", "submitted"),
        ("submitted", "accepted"),
    ]


def test_timeout_becomes_reconciliation_required_not_false_rejection(monkeypatch):
    repo = _repository()
    transaction = _queued_adjustment(repo)
    monkeypatch.setattr(
        "modules.traceability.processor.submit_package_adjustment",
        lambda **kwargs: {
            "ok": False,
            "status": "timeout",
            "message": "Metrc did not respond before the timeout.",
        },
    )

    result = process_transaction(
        repo,
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        credentials=_credentials(),
    )

    assert result.status == "reconciliation_required"
    assert result.error_code == "timeout"
    assert "timeout" in result.error_message.casefold()


def test_definite_provider_rejection_becomes_rejected(monkeypatch):
    repo = _repository()
    transaction = _queued_adjustment(repo)
    monkeypatch.setattr(
        "modules.traceability.processor.submit_package_adjustment",
        lambda **kwargs: {
            "ok": False,
            "status": "forbidden",
            "http_status": 403,
            "message": "Metrc authenticated the keys, but this user lacks permission.",
        },
    )

    result = process_transaction(
        repo,
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        credentials=_credentials(),
    )

    assert result.status == "rejected"
    assert result.error_code == "forbidden"
    assert repo.list_attempts("org-1", "fac-1", transaction.id)[0].http_status == 403


def test_provider_worker_refuses_nonqueued_transaction_and_mismatched_credentials():
    repo = _repository()
    requested = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="PKG-2",
        idempotency_key="adjustment:test:2",
        actor="operator",
    )
    with pytest.raises(ValueError, match="Only queued"):
        process_transaction(
            repo,
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=requested.id,
            credentials=_credentials(),
        )

    queued = _queued_adjustment(repo)
    with pytest.raises(ValueError, match="do not match"):
        process_transaction(
            repo,
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=queued.id,
            credentials=TraceabilityCredentials(provider="biotrack"),
        )
