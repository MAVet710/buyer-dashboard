import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, Organization
from modules.traceability.models import TraceabilityTransaction, TraceabilityTransactionAttempt
from modules.traceability.repository import TraceabilityRepository


def _repository():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityTransactionAttempt.__table__.create(engine)

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
        session.add(Organization(id="org-2", name="Other Operator", slug="other-operator"))
        session.add(
            Facility(
                id="fac-2",
                organization_id="org-2",
                name="Other Facility",
                code="OTHER",
            )
        )
    return TraceabilityRepository(engine)


def test_traceability_create_is_idempotent_and_redacts_credentials():
    repo = _repository()

    first = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406030000TEST001",
        idempotency_key="adjustment:1A406030000TEST001:001",
        actor="operator@example",
        license_number="MR281234",
        request_payload={
            "Label": "1A406030000TEST001",
            "Quantity": -1,
            "UserApiKey": "never-store-this",
            "nested": {"authorization": "Bearer never-store-this-either"},
        },
    )
    second = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="METRC",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406030000TEST001",
        idempotency_key="adjustment:1A406030000TEST001:001",
        actor="operator@example",
    )

    assert first.id == second.id
    payload = json.loads(first.request_payload_json)
    assert payload["Label"] == "1A406030000TEST001"
    assert payload["UserApiKey"] == "[REDACTED]"
    assert payload["nested"]["authorization"] == "[REDACTED]"
    assert "never-store-this" not in first.request_payload_json


def test_traceability_lifecycle_requires_valid_transitions():
    repo = _repository()
    transaction = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="package_create",
        entity_type="package",
        entity_id="local-package-1",
        idempotency_key="package-create:local-package-1",
        actor="qa",
    )

    transaction = repo.transition(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="validated",
        actor="qa",
    )
    transaction = repo.transition(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="queued",
        actor="supervisor",
    )
    transaction = repo.transition(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="submitted",
        actor="system",
    )
    transaction = repo.transition(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="accepted",
        external_reference="METRC-REF-100",
        response_payload={"Id": 100},
    )
    transaction = repo.transition(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="verified",
        actor="system",
    )

    assert transaction.status == "verified"
    assert transaction.external_reference == "METRC-REF-100"
    assert transaction.submitted_at is not None
    assert transaction.completed_at is not None

    with pytest.raises(ValueError, match="not allowed"):
        repo.transition(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="queued",
        )


def test_traceability_attempts_are_ordered_and_reconciliation_is_tenant_safe():
    repo = _repository()
    transaction = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="biotrack",
        operation_type="transfer_submit",
        entity_type="transfer",
        entity_id="transfer-44",
        idempotency_key="transfer-submit:44",
        actor="operator",
    )
    for status in ("validated", "queued", "submitted"):
        transaction = repo.transition(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status=status,
            actor="operator",
        )

    repo.record_attempt(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        request_payload={"transfer": 44},
        http_status=503,
        error_code="SERVICE_UNAVAILABLE",
        error_message="Provider unavailable",
    )
    repo.record_attempt(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        request_payload={"transfer": 44},
        response_payload={"accepted": False},
        http_status=400,
        error_code="VALIDATION",
        error_message="External quantity conflict",
    )
    transaction = repo.transition(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="reconciliation_required",
        error_code="STATE_CONFLICT",
        error_message="Buyer Dash and external state differ",
    )

    attempts = repo.list_attempts("org-1", "fac-1", transaction.id)
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert repo.get_transaction("org-1", "fac-1", transaction.id).attempt_count == 2

    reconciliation = repo.list_reconciliation_queue("org-1", "fac-1")
    assert [item.id for item in reconciliation] == [transaction.id]
    assert repo.list_reconciliation_queue("org-2", "fac-2") == []

    with pytest.raises(ValueError, match="active facility"):
        repo.get_transaction("org-2", "fac-2", transaction.id)
