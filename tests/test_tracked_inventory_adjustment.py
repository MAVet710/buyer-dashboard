from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import (
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
)
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
    return engine


def _credentials(dispatch=None):
    return SimpleNamespace(
        configured=True,
        status="connected",
        trusted_mapping=True,
        state="MA",
        environment="sandbox",
        user_api_key="runtime-user",
        integrator_api_key="runtime-integrator",
        license_number="MR123",
        provider_dispatch=dispatch,
    )


def _accepted_dispatch(repository: TraceabilityBackofficeRepository):
    def dispatch(transaction_id: str):
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="submitted",
            actor="worker",
            reason="submit",
            source="provider_worker",
        )
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="accepted",
            actor="worker",
            reason="accepted; readback pending",
            source="provider_worker",
        )
        return {"ok": True, "status": "accepted", "verified": False}

    return dispatch


def test_tracked_inventory_adjustment_records_local_state_but_waits_for_readback():
    engine = _engine()
    repository = TraceabilityBackofficeRepository(engine)
    local_calls = []

    delta, unit, transaction_id = run_tracked_metrc_adjustment(
        organization_id="org-1",
        facility_id="fac-1",
        actor="admin",
        credentials=_credentials(_accepted_dispatch(repository)),
        package_id="PKG-1",
        adjustment_type="incremental",
        quantity=-2,
        unit="g",
        reason="Scale Variance",
        reason_note="Count correction",
        local_apply=lambda: (local_calls.append(True) or -2.0, "g"),
        repository=repository,
    )

    assert (delta, unit) == (-2.0, "g")
    assert local_calls == [True]
    transaction = repository.get_transaction("org-1", "fac-1", transaction_id)
    assert transaction.status == "accepted"
    assert transaction.operation_type == "package_adjust"
    assert json.loads(transaction.readback_result_json)["status"] == "pending"
    assert json.loads(transaction.local_state_json)["inventory_write_applied"] is True
    assert "runtime-user" not in transaction.request_payload_json
    assert "runtime-integrator" not in transaction.request_payload_json


def test_tracked_inventory_adjustment_does_not_apply_local_when_provider_not_accepted():
    engine = _engine()
    repository = TraceabilityBackofficeRepository(engine)

    def dispatch(transaction_id: str):
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="submitted",
            actor="worker",
            reason="submit",
            source="provider_worker",
        )
        repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction_id,
            new_status="reconciliation_required",
            actor="worker",
            reason="timeout",
            source="provider_worker",
            error_code="timeout",
            error_message="Metrc did not respond before the timeout.",
        )
        return {"ok": False, "status": "reconciliation_required"}

    local_calls = []
    with pytest.raises(RuntimeError, match="timeout"):
        run_tracked_metrc_adjustment(
            organization_id="org-1",
            facility_id="fac-1",
            actor="admin",
            credentials=_credentials(dispatch),
            package_id="PKG-1",
            adjustment_type="incremental",
            quantity=-2,
            unit="g",
            reason="Scale Variance",
            reason_note="",
            local_apply=lambda: (local_calls.append(True) or -2.0, "g"),
            repository=repository,
        )
    assert local_calls == []


def test_local_failure_after_external_acceptance_becomes_reconciliation_required():
    engine = _engine()
    repository = TraceabilityBackofficeRepository(engine)

    def explode():
        raise RuntimeError("local database unavailable")

    with pytest.raises(RuntimeError, match="local database unavailable"):
        run_tracked_metrc_adjustment(
            organization_id="org-1",
            facility_id="fac-1",
            actor="admin",
            credentials=_credentials(_accepted_dispatch(repository)),
            package_id="PKG-1",
            adjustment_type="absolute",
            quantity=8,
            unit="g",
            reason="Count correction",
            reason_note="",
            local_apply=explode,
            repository=repository,
        )

    rows = repository.list_transactions("org-1", "fac-1")
    assert len(rows) == 1
    assert rows[0].status == "reconciliation_required"
    assert rows[0].error_code == "local_persistence_failed"
    assert "local database unavailable" in rows[0].error_message


def test_tracked_adjustment_has_no_legacy_provider_fallback():
    engine = _engine()
    repository = TraceabilityBackofficeRepository(engine)

    with pytest.raises(ValueError, match="canonical traceability dispatcher"):
        run_tracked_metrc_adjustment(
            organization_id="org-1",
            facility_id="fac-1",
            actor="admin",
            credentials=_credentials(None),
            package_id="PKG-1",
            adjustment_type="incremental",
            quantity=-1,
            unit="g",
            reason="Count correction",
            reason_note="",
            local_apply=lambda: (-1.0, "g"),
            repository=repository,
        )

    assert repository.list_transactions("org-1", "fac-1") == []
