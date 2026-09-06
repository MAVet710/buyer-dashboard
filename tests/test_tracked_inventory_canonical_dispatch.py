from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.inventory_adjustment import run_tracked_metrc_adjustment
from modules.traceability.models import TraceabilityStatusEvent, TraceabilityTransaction, TraceabilityTransactionAttempt


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    Product.__table__.create(engine)
    InventoryLot.__table__.create(engine)
    InventoryTransaction.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityTransactionAttempt.__table__.create(engine)
    TraceabilityStatusEvent.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1", name="Demo", slug="demo"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Store", code="STORE"))
    return engine, TraceabilityBackofficeRepository(engine)


def _credentials():
    return SimpleNamespace(
        configured=True,
        status="connected",
        trusted_mapping=True,
        state="MA",
        environment="sandbox",
        user_api_key="runtime-user",
        integrator_api_key="runtime-integrator",
        license_number="MR123",
    )


def test_canonical_dispatch_keeps_provider_acceptance_unverified_until_readback():
    _engine, repository = _setup()
    local_calls = []

    def dispatch(transaction_id: str):
        tx = repository.get_transaction("org-1", "fac-1", transaction_id)
        assert tx.operation_type == "package_adjust"
        payload = json.loads(tx.request_payload_json)
        assert payload["quantity_delta"] == -2.0
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="submitted",
            actor="provider-worker",
            reason="provider request sent",
            source="provider_worker",
        )
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="accepted",
            actor="provider-worker",
            reason="provider accepted; readback pending",
            source="provider_worker",
        )
        return {"ok": True, "status": "accepted", "verified": False}

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
        provider_dispatch=dispatch,
        repository=repository,
    )

    assert (delta, unit) == (-2.0, "g")
    assert local_calls == [True]
    tx = repository.get_transaction("org-1", "fac-1", transaction_id)
    assert tx.status == "accepted"
    assert tx.operation_type == "package_adjust"
    assert json.loads(tx.readback_result_json)["status"] == "pending"
    local_state = json.loads(tx.local_state_json)
    assert local_state["inventory_write_applied"] is True
    assert local_state["quantity_delta"] == -2.0
    evidence = json.loads(tx.reconciliation_evidence_json)
    assert evidence["verification_pending"] is True
    assert "runtime-user" not in tx.request_payload_json
    assert "runtime-integrator" not in tx.request_payload_json


def test_canonical_dispatch_does_not_apply_local_state_when_provider_needs_reconciliation():
    _engine, repository = _setup()
    local_calls = []

    def dispatch(transaction_id: str):
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="submitted",
            actor="provider-worker",
            reason="provider request sent",
            source="provider_worker",
        )
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="reconciliation_required",
            actor="provider-worker",
            reason="request outcome uncertain",
            source="provider_worker",
            error_code="retryable_provider_error",
            error_message="Metrc request outcome is uncertain.",
        )
        return {"ok": False, "status": "reconciliation_required", "verified": False}

    with pytest.raises(RuntimeError, match="uncertain"):
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
            provider_dispatch=dispatch,
            repository=repository,
        )

    assert local_calls == []
    tx = repository.list_transactions("org-1", "fac-1")[0]
    assert tx.status == "reconciliation_required"
