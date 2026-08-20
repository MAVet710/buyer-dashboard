"""Deterministic execution registry for human-approved Doobie actions."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any, Callable

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, utc_now
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.service import CommercialFinanceService
from modules.production_erp.service import ProductionERPService
from modules.traceability.backoffice import TraceabilityBackofficeRepository

from .models import ActionExecution, ActionProposal


ALLOWED_ACTIONS = {
    "create_purchase_order",
    "create_production_order",
    "reserve_production_materials",
    "send_invoice",
    "queue_traceability",
}


class DoobieActionService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.handlers: dict[str, Callable[[ActionProposal, dict[str, Any], str], dict[str, Any]]] = {
            "create_purchase_order": self._create_purchase_order,
            "create_production_order": self._create_production_order,
            "reserve_production_materials": self._reserve_production_materials,
            "send_invoice": self._send_invoice,
            "queue_traceability": self._queue_traceability,
        }

    def propose(
        self,
        *,
        organization_id: str,
        facility_id: str,
        action_type: str,
        title: str,
        rationale: str,
        payload: dict[str, Any],
        preview: dict[str, Any],
        actor: str,
        idempotency_key: str,
        financial_impact_usd: float = 0.0,
        risk_level: str = "medium",
        source_type: str = "manual",
        source_id: str = "",
    ) -> ActionProposal:
        action_type = str(action_type or "").strip()
        if action_type not in ALLOWED_ACTIONS:
            raise ValueError("Action type is not registered for deterministic execution.")
        if not str(idempotency_key or "").strip():
            raise ValueError("Action proposal requires an idempotency key.")
        risk_level = str(risk_level or "medium").strip().casefold()
        if risk_level not in {"low","medium","high","compliance"}:
            raise ValueError("Unsupported action risk level.")
        with self._sessions.begin() as session:
            existing = session.scalar(select(ActionProposal).where(ActionProposal.organization_id == organization_id, ActionProposal.idempotency_key == idempotency_key))
            if existing:
                return existing
            proposal = ActionProposal(
                organization_id=organization_id,
                facility_id=facility_id,
                idempotency_key=idempotency_key,
                action_type=action_type,
                title=str(title or action_type),
                rationale=str(rationale or ""),
                payload_json=json.dumps(payload or {}, default=str, sort_keys=True),
                preview_json=json.dumps(preview or {}, default=str, sort_keys=True),
                financial_impact_usd=max(0.0, float(financial_impact_usd or 0)),
                risk_level=risk_level,
                status="proposed",
                source_type=str(source_type or "manual"),
                source_id=str(source_id or ""),
                created_by=str(actor or "system"),
            )
            session.add(proposal); session.flush()
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="action_proposal", entity_id=proposal.id, action="proposed", actor=str(actor or "system"), changes_json=json.dumps({"action_type": action_type, "risk_level": risk_level}, sort_keys=True)))
            return proposal

    def list_proposals(self, organization_id: str, facility_id: str, *, statuses: tuple[str, ...] = ("proposed","approved","failed"), limit: int = 100) -> list[ActionProposal]:
        with self._sessions() as session:
            return list(session.scalars(select(ActionProposal).where(ActionProposal.organization_id == organization_id, ActionProposal.facility_id == facility_id, ActionProposal.status.in_(statuses)).order_by(ActionProposal.financial_impact_usd.desc(), ActionProposal.created_at.desc()).limit(max(1, min(limit, 500)))))

    def approve(self, *, organization_id: str, facility_id: str, proposal_id: str, actor: str) -> ActionProposal:
        with self._sessions.begin() as session:
            proposal = session.get(ActionProposal, proposal_id)
            if not proposal or proposal.organization_id != organization_id or proposal.facility_id != facility_id:
                raise ValueError("Action proposal was not found in the active facility.")
            if proposal.status not in {"proposed","failed"}:
                raise ValueError("Only proposed or failed actions can be approved.")
            if proposal.expires_at and proposal.expires_at < utc_now():
                proposal.status = "expired"
                raise ValueError("This proposal has expired and must be regenerated.")
            proposal.status = "approved"
            proposal.approved_by = str(actor or "system")
            proposal.approved_at = utc_now()
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="action_proposal", entity_id=proposal.id, action="approved", actor=str(actor or "system"), changes_json="{}"))
            return proposal

    def reject(self, *, organization_id: str, facility_id: str, proposal_id: str, actor: str) -> ActionProposal:
        with self._sessions.begin() as session:
            proposal = session.get(ActionProposal, proposal_id)
            if not proposal or proposal.organization_id != organization_id or proposal.facility_id != facility_id:
                raise ValueError("Action proposal was not found in the active facility.")
            if proposal.status == "executed":
                raise ValueError("Executed actions cannot be rejected retroactively.")
            proposal.status = "rejected"
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="action_proposal", entity_id=proposal.id, action="rejected", actor=str(actor or "system"), changes_json="{}"))
            return proposal

    def execute(self, *, organization_id: str, facility_id: str, proposal_id: str, actor: str) -> dict[str, Any]:
        with self._sessions.begin() as session:
            proposal = session.get(ActionProposal, proposal_id)
            if not proposal or proposal.organization_id != organization_id or proposal.facility_id != facility_id:
                raise ValueError("Action proposal was not found in the active facility.")
            if proposal.status == "executed":
                latest = session.scalar(select(ActionExecution).where(ActionExecution.proposal_id == proposal.id, ActionExecution.status == "succeeded").order_by(ActionExecution.attempt_number.desc()).limit(1))
                return json.loads(latest.result_json or "{}") if latest else {"status": "already_executed"}
            if proposal.status != "approved":
                raise ValueError("Approve the preview before executing this action.")
            attempt_number = int(session.scalar(select(func.coalesce(func.max(ActionExecution.attempt_number), 0)).where(ActionExecution.proposal_id == proposal.id)) or 0) + 1
            execution = ActionExecution(organization_id=organization_id, facility_id=facility_id, proposal_id=proposal.id, attempt_number=attempt_number, status="started", actor=str(actor or "system"))
            session.add(execution)
            proposal.status = "executing"
            session.flush()

        payload = json.loads(proposal.payload_json or "{}")
        handler = self.handlers[proposal.action_type]
        try:
            result = handler(proposal, payload, str(actor or "system"))
        except Exception as exc:
            with self._sessions.begin() as session:
                current = session.get(ActionProposal, proposal.id)
                execution = session.scalar(select(ActionExecution).where(ActionExecution.proposal_id == proposal.id, ActionExecution.attempt_number == attempt_number))
                current.status = "failed"
                execution.status = "failed"
                execution.error_message = f"{type(exc).__name__}: {str(exc)}"[:4000]
                execution.completed_at = utc_now()
                session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="action_proposal", entity_id=proposal.id, action="execution_failed", actor=str(actor or "system"), changes_json=json.dumps({"error_type": type(exc).__name__})))
            raise

        with self._sessions.begin() as session:
            current = session.get(ActionProposal, proposal.id)
            execution = session.scalar(select(ActionExecution).where(ActionExecution.proposal_id == proposal.id, ActionExecution.attempt_number == attempt_number))
            current.status = "executed"
            execution.status = "succeeded"
            execution.result_json = json.dumps(result or {}, default=str, sort_keys=True)
            execution.completed_at = utc_now()
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="action_proposal", entity_id=proposal.id, action="executed", actor=str(actor or "system"), changes_json=execution.result_json))
        return result

    def _create_purchase_order(self, proposal: ActionProposal, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        raw_due = payload.get("due_date")
        due = date.fromisoformat(raw_due) if raw_due else None
        order = CommercialRepository(self.engine).create_order(
            organization_id=proposal.organization_id,
            facility_id=proposal.facility_id,
            partner_id=str(payload["partner_id"]),
            order_number=str(payload["order_number"]),
            order_type="purchase",
            order_date=date.fromisoformat(str(payload.get("order_date") or date.today().isoformat())),
            due_date=due,
            lines=list(payload.get("lines") or []),
            actor=actor,
            external_reference=str(payload.get("external_reference") or ""),
            notes=str(payload.get("notes") or "Created from approved Doobie action."),
        )
        return {"commercial_order_id": order.id, "order_number": order.order_number, "action": "purchase_order_created"}

    def _create_production_order(self, proposal: ActionProposal, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        raw_due = payload.get("due_at")
        due_at = datetime.fromisoformat(raw_due) if raw_due else None
        order = ComanRepository(self.engine).create_production_order(
            organization_id=proposal.organization_id,
            facility_id=proposal.facility_id,
            order_number=str(payload["order_number"]),
            work_type=str(payload.get("work_type") or "internal"),
            product_name=str(payload["product_name"]),
            product_format=str(payload.get("product_format") or "Other"),
            requested_units=int(payload.get("requested_units") or 0),
            actor=actor,
            customer_id=payload.get("customer_id") or None,
            due_at=due_at,
            sku=str(payload.get("sku") or ""),
            priority=str(payload.get("priority") or "normal"),
            notes=str(payload.get("notes") or "Created from approved Doobie action."),
        )
        return {"production_order_id": order.id, "order_number": order.order_number, "action": "production_order_created"}

    def _reserve_production_materials(self, proposal: ActionProposal, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        result = ProductionERPService(self.engine).reserve_bom_materials(organization_id=proposal.organization_id, facility_id=proposal.facility_id, order_id=str(payload["production_order_id"]), actor=actor)
        return {"action": "materials_reserved", **result}

    def _send_invoice(self, proposal: ActionProposal, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        invoice = CommercialFinanceService(self.engine).send_invoice(organization_id=proposal.organization_id, facility_id=proposal.facility_id, invoice_id=str(payload["invoice_id"]))
        return {"action": "invoice_sent", "invoice_id": invoice.id, "status": invoice.status}

    def _queue_traceability(self, proposal: ActionProposal, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        repo = TraceabilityBackofficeRepository(self.engine)
        tx = repo.create_transaction(
            organization_id=proposal.organization_id,
            facility_id=proposal.facility_id,
            provider=str(payload.get("provider") or "metrc"),
            operation_type=str(payload["operation_type"]),
            entity_type=str(payload["entity_type"]),
            entity_id=str(payload["entity_id"]),
            idempotency_key=f"doobie-action:{proposal.id}",
            actor=actor,
            license_number=str(payload.get("license_number") or ""),
            request_payload=dict(payload.get("request_payload") or {}),
            reason=str(payload.get("reason") or proposal.rationale or proposal.title),
        )
        if tx.status == "requested":
            tx = repo.transition_logged(organization_id=proposal.organization_id, facility_id=proposal.facility_id, transaction_id=tx.id, new_status="validated", actor=actor, reason="Approved Doobie action validated for provider queue.", source="system")
        if tx.status == "validated":
            tx = repo.transition_logged(organization_id=proposal.organization_id, facility_id=proposal.facility_id, transaction_id=tx.id, new_status="queued", actor=actor, reason="Approved Doobie action queued; provider worker submission remains separately auditable.", source="system")
        return {"action": "traceability_queued", "transaction_id": tx.id, "status": tx.status}
