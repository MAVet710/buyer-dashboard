from pathlib import Path

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
from modules.traceability.ui import can_manage_traceability, transaction_rows


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
        session.add(Organization(id="org-2", name="Other Operator", slug="other-operator"))
        session.add(
            Facility(
                id="fac-2",
                organization_id="org-2",
                name="Other Facility",
                code="OTHER",
            )
        )
    return TraceabilityBackofficeRepository(engine)


def _transaction(repo):
    return repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406030000TEST001",
        idempotency_key="adjustment:1A406030000TEST001:1",
        actor="operator",
        license_number="MR281234",
    )


def test_logged_transitions_create_append_only_actor_reason_history():
    repo = _repository()
    transaction = _transaction(repo)

    for status in ("validated", "queued", "submitted"):
        transaction = repo.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status=status,
            actor="system-worker",
            reason=f"Advance to {status}",
            source="system",
        )
    transaction = repo.transition_logged(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        new_status="reconciliation_required",
        actor="system-worker",
        reason="External quantity differs",
        source="system",
        error_code="STATE_CONFLICT",
        error_message="Buyer Dash and METRC quantities differ",
    )
    transaction = repo.requeue_manual(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=transaction.id,
        actor="qa@example",
        reason="Reviewed package history; retry is appropriate",
    )

    assert transaction.status == "queued"
    events = repo.list_status_events("org-1", "fac-1", transaction.id)
    assert [(event.from_status, event.to_status) for event in events][-2:] == [
        ("submitted", "reconciliation_required"),
        ("reconciliation_required", "queued"),
    ]
    assert events[-1].actor == "qa@example"
    assert events[-1].source == "manual"
    assert "Reviewed package history" in events[-1].reason


def test_manual_traceability_actions_require_reason_and_follow_state_machine():
    repo = _repository()
    transaction = _transaction(repo)

    with pytest.raises(ValueError, match="reason is required"):
        repo.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status="cancelled",
            actor="supervisor",
            source="manual",
        )

    with pytest.raises(ValueError, match="not allowed"):
        repo.verify_manual(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            actor="supervisor",
            reason="Cannot verify a merely requested action",
        )


def test_backoffice_queue_summary_filters_and_tenant_scope():
    repo = _repository()
    first = _transaction(repo)
    repo.transition_logged(
        organization_id="org-1",
        facility_id="fac-1",
        transaction_id=first.id,
        new_status="validated",
        actor="system",
    )

    second = repo.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="biotrack",
        operation_type="transfer_submit",
        entity_type="transfer",
        entity_id="T-2",
        idempotency_key="transfer:T-2",
        actor="operator",
    )
    for status in ("validated", "queued", "submitted", "rejected"):
        second = repo.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=second.id,
            new_status=status,
            actor="system",
            error_message="Rejected" if status == "rejected" else "",
        )

    summary = repo.summary("org-1", "fac-1")
    assert summary["total"] == 2
    assert summary["in_flight"] == 1
    assert summary["needs_reconciliation"] == 1
    assert repo.summary("org-2", "fac-2")["total"] == 0

    rejected = repo.list_transactions(
        "org-1",
        "fac-1",
        statuses=("rejected",),
    )
    assert [item.id for item in rejected] == [second.id]
    assert repo.list_transactions("org-1", "fac-1", provider="metrc")[0].id == first.id


def test_traceability_console_helpers_are_role_safe_and_hide_internal_ids_from_table():
    repo = _repository()
    transaction = _transaction(repo)
    frame = transaction_rows([transaction])

    assert frame.iloc[0]["Provider"] == "METRC"
    assert frame.iloc[0]["Entity"] == "1A406030000TEST001"
    assert can_manage_traceability({"auth_user_role": "qa"}) is True
    assert can_manage_traceability({"auth_user_role": "buyer"}) is False
    assert can_manage_traceability({"auth_user_role": "read_only"}) is False


def test_operations_home_exposes_traceability_work_window_without_pos_surface():
    home_source = Path("modules/navigation/role_home.py").read_text(encoding="utf-8")
    scope_source = Path("docs/BACKOFFICE_SCOPE.md").read_text(encoding="utf-8")

    assert "Traceability queue" in home_source
    assert "traceability_console_open" in home_source
    assert "render_traceability_console_dialog" in home_source
    assert "separate app" in scope_source.lower()
    assert "backoffice" in scope_source.lower()
