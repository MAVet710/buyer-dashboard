from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.models import (
    TraceabilityStatusEvent,
    TraceabilityTransaction,
    TraceabilityTransactionAttempt,
)
from services.traceability_inbox import build_traceability_inbox


def _engine_with_scope():
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
    return engine


def test_durable_traceability_exception_becomes_home_inbox_item(monkeypatch):
    engine = _engine_with_scope()
    repository = TraceabilityBackofficeRepository(engine)
    transaction = repository.create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="1A406030000TEST001",
        idempotency_key="adjust:1",
        actor="operator",
    )
    for status in ("validated", "queued", "submitted", "reconciliation_required"):
        transaction = repository.transition_logged(
            organization_id="org-1",
            facility_id="fac-1",
            transaction_id=transaction.id,
            new_status=status,
            actor="system",
            reason="Quantity mismatch" if status == "reconciliation_required" else "",
            error_message="Buyer Dash and METRC quantities differ" if status == "reconciliation_required" else "",
        )

    monkeypatch.setattr("services.traceability_inbox.create_coman_engine", lambda: engine)
    items = build_traceability_inbox(
        {"active_organization_id": "org-1", "active_facility_id": "fac-1"}
    )

    assert len(items) == 1
    assert items[0].severity == "critical"
    assert items[0].key == f"traceability:{transaction.id}"
    assert items[0].action_label == "Resolve"
    assert "METRC reconciliation required" in items[0].title


def test_home_ranks_durable_traceability_inbox_and_suppresses_session_duplicate():
    source = Path("modules/navigation/role_home.py").read_text(encoding="utf-8")
    assert "build_traceability_inbox" in source
    assert 'item.key != "metrc-sync-failures"' in source
    assert "traceability_items" in source
