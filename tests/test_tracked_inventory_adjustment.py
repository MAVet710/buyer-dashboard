from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.inventory_adjustment import run_tracked_metrc_adjustment
from modules.traceability.models import (
    TraceabilityStatusEvent,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityTransactionAttempt.__table__.create(engine)
    TraceabilityStatusEvent.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1", name="Demo", slug="demo"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Store", code="STORE"))
    return engine


def _credentials():
    return SimpleNamespace(
        configured=True,
        state="MA",
        user_api_key="runtime-user",
        integrator_api_key="runtime-integrator",
        license_number="MR123",
    )


def test_tracked_inventory_adjustment_verifies_only_after_local_persistence(monkeypatch):
    engine = _engine()
    monkeypatch.setattr("modules.traceability.inventory_adjustment.create_coman_engine", lambda: engine)

    def fake_process(repository, **kwargs):
        transaction = repository.get_transaction("org-1", "fac-1", kwargs["transaction_id"])
        transaction = repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="submitted",
            actor="worker",
            reason="submit",
        )
        return repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="accepted",
            actor="worker",
            reason="accepted",
        )

    monkeypatch.setattr("modules.traceability.inventory_adjustment.process_transaction", fake_process)
    local_calls = []
    delta, unit, transaction_id = run_tracked_metrc_adjustment(
        organization_id="org-1",
        facility_id="fac-1",
        actor="admin",
        credentials=_credentials(),
        package_id="PKG-1",
        adjustment_type="incremental",
        quantity=-2,
        unit="g",
        reason="Scale Variance",
        reason_note="Count correction",
        local_apply=lambda: (local_calls.append(True) or -2.0, "g"),
    )

    assert (delta, unit) == (-2.0, "g")
    assert local_calls == [True]
    repository = TraceabilityBackofficeRepository(engine)
    transaction = repository.get_transaction("org-1", "fac-1", transaction_id)
    assert transaction.status == "verified"
    assert "runtime-user" not in transaction.request_payload_json
    assert "runtime-integrator" not in transaction.request_payload_json


def test_tracked_inventory_adjustment_does_not_apply_local_when_provider_not_accepted(monkeypatch):
    engine = _engine()
    monkeypatch.setattr("modules.traceability.inventory_adjustment.create_coman_engine", lambda: engine)

    def fake_process(repository, **kwargs):
        transaction = repository.get_transaction("org-1", "fac-1", kwargs["transaction_id"])
        transaction = repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="submitted",
            actor="worker",
            reason="submit",
        )
        return repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="reconciliation_required",
            actor="worker",
            reason="timeout",
            error_code="timeout",
            error_message="Metrc did not respond before the timeout.",
        )

    monkeypatch.setattr("modules.traceability.inventory_adjustment.process_transaction", fake_process)
    local_calls = []
    with pytest.raises(RuntimeError, match="timeout"):
        run_tracked_metrc_adjustment(
            organization_id="org-1",
            facility_id="fac-1",
            actor="admin",
            credentials=_credentials(),
            package_id="PKG-1",
            adjustment_type="incremental",
            quantity=-2,
            unit="g",
            reason="Scale Variance",
            reason_note="",
            local_apply=lambda: (local_calls.append(True) or -2.0, "g"),
        )
    assert local_calls == []


def test_local_failure_after_external_acceptance_becomes_reconciliation_required(monkeypatch):
    engine = _engine()
    monkeypatch.setattr("modules.traceability.inventory_adjustment.create_coman_engine", lambda: engine)

    def fake_process(repository, **kwargs):
        transaction = repository.get_transaction("org-1", "fac-1", kwargs["transaction_id"])
        transaction = repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="submitted",
            actor="worker",
            reason="submit",
        )
        return repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="accepted",
            actor="worker",
            reason="accepted",
        )

    monkeypatch.setattr("modules.traceability.inventory_adjustment.process_transaction", fake_process)

    def explode():
        raise RuntimeError("local database unavailable")

    with pytest.raises(RuntimeError, match="local database unavailable"):
        run_tracked_metrc_adjustment(
            organization_id="org-1",
            facility_id="fac-1",
            actor="admin",
            credentials=_credentials(),
            package_id="PKG-1",
            adjustment_type="absolute",
            quantity=8,
            unit="g",
            reason="Count correction",
            reason_note="",
            local_apply=explode,
        )

    repository = TraceabilityBackofficeRepository(engine)
    rows = repository.list_transactions("org-1", "fac-1")
    assert len(rows) == 1
    assert rows[0].status == "reconciliation_required"
    assert rows[0].error_code == "local_persistence_failed"
    assert "local database unavailable" in rows[0].error_message
