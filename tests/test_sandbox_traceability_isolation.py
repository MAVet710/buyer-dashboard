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
from modules.traceability.processor import TraceabilityCredentials, process_transaction


def _sandbox_repository():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityTransactionAttempt.__table__.create(engine)
    TraceabilityStatusEvent.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-sbx", name="DEV Sandbox", slug="dev-sandbox"))
        session.add(
            Facility(
                id="fac-sbx",
                organization_id="org-sbx",
                name="Sandbox Facility",
                code="SANDBOX",
            )
        )
    return TraceabilityBackofficeRepository(engine)


def _queued_transaction(repo):
    transaction = repo.create_transaction(
        organization_id="org-sbx",
        facility_id="fac-sbx",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A4-SANDBOX-TEST",
        idempotency_key="sandbox:provider:block",
        actor="dev",
        license_number="MR-SANDBOX",
        request_payload={
            "package_label": "1A4-SANDBOX-TEST",
            "adjustment_type": "incremental",
            "quantity": -1.0,
            "unit": "g",
            "reason": "Sandbox test",
        },
    )
    transaction = repo.transition_logged(
        organization_id="org-sbx",
        facility_id="fac-sbx",
        transaction_id=transaction.id,
        new_status="validated",
        actor="dev",
        reason="Sandbox validation",
    )
    return repo.transition_logged(
        organization_id="org-sbx",
        facility_id="fac-sbx",
        transaction_id=transaction.id,
        new_status="queued",
        actor="dev",
        reason="Sandbox queue test",
    )


def test_dev_sandbox_traceability_never_calls_real_provider(monkeypatch):
    repo = _sandbox_repository()
    transaction = _queued_transaction(repo)

    def provider_must_not_run(**kwargs):
        raise AssertionError("DEV Sandbox attempted a real METRC provider call")

    monkeypatch.setattr(
        "modules.traceability.processor.submit_package_adjustment",
        provider_must_not_run,
    )

    credentials = TraceabilityCredentials(
        provider="metrc",
        state="MA",
        user_api_key="real-looking-user-key",
        integrator_api_key="real-looking-integrator-key",
        license_number="MR-SANDBOX",
    )
    with pytest.raises(ValueError, match="simulation-only"):
        process_transaction(
            repo,
            organization_id="org-sbx",
            facility_id="fac-sbx",
            transaction_id=transaction.id,
            credentials=credentials,
            actor="dev",
        )

    persisted = repo.get_transaction("org-sbx", "fac-sbx", transaction.id)
    assert persisted.status == "queued"
    assert repo.list_attempts("org-sbx", "fac-sbx", transaction.id) == []
