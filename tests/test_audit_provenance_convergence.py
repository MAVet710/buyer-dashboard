from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.audit import record_audit_event
from modules.coman.models import AuditEvent, Base
from modules.coman.repository import ComanRepository
from modules.doobie_actions.models import ActionExecution, ActionProposal  # noqa: F401 - register tables
from modules.doobie_actions.service import DoobieActionService
from modules.hardware_capture_provenance import IdentifierCaptureProvenance


def _source(event: AuditEvent) -> str:
    return str(json.loads(event.changes_json)["_event"]["source"])


def test_human_scanner_rfid_and_ai_share_the_authoritative_audit_ledger():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    org = coman.create_organization("Provenance Convergence QA")
    facility = coman.create_facility(org.id, "Main", "MAIN")

    scanner = IdentifierCaptureProvenance.build(
        source="camera",
        device_id="phone-camera-1",
        symbology="QR",
        captured_at="2026-09-06T20:00:00-04:00",
    )
    rfid = IdentifierCaptureProvenance.build(
        source="rfid_reader",
        device_id="rfid-reader-1",
        symbology="EPC",
        captured_at="2026-09-06T20:00:01-04:00",
    )

    with Session(engine) as session:
        record_audit_event(
            session,
            organization_id=org.id,
            facility_id=facility.id,
            entity_type="inventory_lot",
            entity_id="lot-human",
            action="physical_count_reviewed",
            actor="operator-1",
            source="user",
            correlation_id="count:human-1",
            metadata={"deterministic_service": "InventoryAuditRepository"},
        )
        record_audit_event(
            session,
            organization_id=org.id,
            facility_id=facility.id,
            entity_type="inventory_lot",
            entity_id="lot-scanner",
            action="capture_verified",
            actor="operator-1",
            source=scanner.audit_source,
            correlation_id="warehouse_pick:scanner-1",
            device=scanner.device_metadata(),
            metadata={"capture_is_authorization": False, "deterministic_service": "CommercialRepository"},
        )
        record_audit_event(
            session,
            organization_id=org.id,
            facility_id=facility.id,
            entity_type="inventory_lot",
            entity_id="lot-rfid",
            action="capture_verified",
            actor="operator-1",
            source=rfid.audit_source,
            correlation_id="warehouse_pick:rfid-1",
            device=rfid.device_metadata(),
            metadata={"capture_is_authorization": False, "deterministic_service": "CommercialRepository"},
        )
        session.commit()

    ai = DoobieActionService(engine)
    proposal = ai.propose(
        organization_id=org.id,
        facility_id=facility.id,
        action_type="create_purchase_order",
        title="Draft supplier replenishment",
        rationale="Agent found a reviewed buying opportunity.",
        payload={},
        preview={"summary": "Human approval is still required."},
        actor="doobie-agent-runtime",
        idempotency_key="provenance-convergence-ai-1",
        source_type="doobie_agent",
        source_id="agent-run-convergence-1",
    )

    with Session(engine) as session:
        events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at, AuditEvent.id)))
        sources = {_source(event) for event in events}
        assert {"user", "scanner", "rfid", "ai_agent"}.issubset(sources)

        scanner_event = next(event for event in events if event.entity_id == "lot-scanner")
        scanner_payload = json.loads(scanner_event.changes_json)["_event"]
        assert scanner_payload["device"]["device_id"] == "phone-camera-1"
        assert scanner_payload["metadata"]["capture_is_authorization"] is False

        rfid_event = next(event for event in events if event.entity_id == "lot-rfid")
        rfid_payload = json.loads(rfid_event.changes_json)["_event"]
        assert rfid_payload["device"]["device_id"] == "rfid-reader-1"
        assert rfid_payload["metadata"]["capture_is_authorization"] is False

        ai_event = next(
            event
            for event in events
            if event.entity_type == "action_proposal" and event.entity_id == proposal.id and event.action == "proposed"
        )
        ai_payload = json.loads(ai_event.changes_json)["_event"]
        assert ai_payload["source"] == "ai_agent"
        assert ai_payload["correlation_id"] == f"doobie_action:{proposal.id}"
        assert ai_payload["metadata"]["proposal_source_id"] == "agent-run-convergence-1"

        # All provenance remains in the one authoritative AuditEvent table; the
        # hardware observations themselves did not create inventory/compliance rows.
        assert {event.__tablename__ for event in events} == {"coman_audit_events"}
