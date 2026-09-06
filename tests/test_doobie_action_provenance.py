from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Base
from modules.coman.repository import ComanRepository
from modules.doobie_actions.models import ActionExecution, ActionProposal  # noqa: F401 - registers tables on Base
from modules.doobie_actions.service import DoobieActionService


def _event(session: Session, proposal_id: str, action: str) -> AuditEvent:
    row = session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "action_proposal",
            AuditEvent.entity_id == proposal_id,
            AuditEvent.action == action,
        )
    )
    assert row is not None
    return row


def test_ai_supported_action_preserves_human_approval_and_canonical_provenance():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    org = coman.create_organization("Doobie Action Provenance QA")
    facility = coman.create_facility(org.id, "Main", "MAIN")
    service = DoobieActionService(engine)

    proposal = service.propose(
        organization_id=org.id,
        facility_id=facility.id,
        action_type="create_purchase_order",
        title="Draft replenishment PO",
        rationale="Agent found a reviewed replenishment opportunity.",
        payload={},
        preview={"summary": "No mutation until human approval."},
        actor="doobie-agent-runtime",
        idempotency_key="qa-ai-proposal-1",
        source_type="doobie_agent",
        source_id="agent-run-42",
    )

    with pytest.raises(ValueError, match="Approve the preview"):
        service.execute(
            organization_id=org.id,
            facility_id=facility.id,
            proposal_id=proposal.id,
            actor="operator-1",
        )

    with Session(engine) as session:
        proposed = json.loads(_event(session, proposal.id, "proposed").changes_json)
        assert proposed["_event"]["source"] == "ai_agent"
        assert proposed["_event"]["correlation_id"] == f"doobie_action:{proposal.id}"
        assert proposed["_event"]["metadata"]["proposal_source_type"] == "doobie_agent"
        assert proposed["_event"]["metadata"]["proposal_source_id"] == "agent-run-42"

    service.approve(
        organization_id=org.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="buyer-1",
    )

    service.handlers["create_purchase_order"] = lambda proposal, payload, actor: {
        "action": "synthetic_purchase_order_created",
        "commercial_order_id": "po-qa-1",
    }
    result = service.execute(
        organization_id=org.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="buyer-1",
    )
    assert result["commercial_order_id"] == "po-qa-1"

    with Session(engine) as session:
        approved_row = _event(session, proposal.id, "approved")
        approved = json.loads(approved_row.changes_json)
        assert approved_row.actor == "buyer-1"
        assert approved["_event"]["source"] == "user"
        assert approved["_event"]["before"]["status"] == "proposed"
        assert approved["_event"]["after"]["status"] == "approved"

        executed_row = _event(session, proposal.id, "executed")
        executed = json.loads(executed_row.changes_json)
        assert executed_row.actor == "buyer-1"
        assert executed["_event"]["source"] == "ai_agent"
        assert executed["_event"]["correlation_id"] == f"doobie_action:{proposal.id}"
        assert executed["_event"]["metadata"]["proposal_source_id"] == "agent-run-42"
        assert executed["_event"]["metadata"]["attempt_number"] == 1
        assert executed["_event"]["after"]["status"] == "executed"
        execution = session.scalar(select(ActionExecution).where(ActionExecution.proposal_id == proposal.id))
        assert execution is not None
        assert executed["_event"]["metadata"]["action_execution_id"] == execution.id
