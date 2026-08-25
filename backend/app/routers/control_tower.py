"""DoobieLogic Control Tower: reconciliation, guarded actions, SOPs, labels, MES, cultivation and commerce."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.commercial.repository import CommercialRepository
from modules.doobie_actions.service import ALLOWED_ACTIONS, DoobieActionService
from modules.operational_moats.intelligence import profitability_360
from modules.operational_moats.service import OperationalMoatService
from modules.traceability.backoffice import MANUAL_TRACEABILITY_ROLES, TraceabilityBackofficeRepository

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine

router = APIRouter(prefix="/control-tower", tags=["control-tower"])
public_router = APIRouter(prefix="/commerce-portal", tags=["commerce-portal"])

ACTION_APPROVERS = {
    "create_purchase_order": {"dev", "admin", "buyer"},
    "create_production_order": {"dev", "admin", "planner", "supervisor"},
    "reserve_production_materials": {"dev", "admin", "planner", "supervisor"},
    "send_invoice": {"dev", "admin", "supervisor"},
    "queue_traceability": {"dev", "admin", "supervisor", "qa"},
}
MUTATION_ROLES = {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}
ADMIN_ROLES = {"dev", "admin"}
COMPLIANCE_ROLES = {"dev", "admin", "supervisor", "qa"}


def _require_role(context: RequestContext, allowed: set[str], message: str = "Your role does not allow this action.") -> None:
    if context.role.casefold() not in allowed:
        raise HTTPException(403, message)


def _dump(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields}


def _trace_row(row: Any) -> dict[str, Any]:
    return _dump(row, ("id", "provider", "operation_type", "entity_type", "entity_id", "license_number", "status", "idempotency_key", "reason", "external_reference", "error_code", "error_message", "attempt_count", "requested_at", "submitted_at", "completed_at", "next_attempt_at", "approved_by"))


def _action_row(row: Any) -> dict[str, Any]:
    data = _dump(row, ("id", "action_type", "title", "rationale", "financial_impact_usd", "risk_level", "status", "source_type", "source_id", "created_by", "approved_by", "approved_at", "expires_at", "created_at", "updated_at"))
    data["payload"] = json.loads(row.payload_json or "{}")
    data["preview"] = json.loads(row.preview_json or "{}")
    return data


class ReasonPayload(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ActionProposalPayload(BaseModel):
    action_type: str
    title: str = Field(min_length=1, max_length=255)
    rationale: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=3, max_length=255)
    financial_impact_usd: float = Field(default=0.0, ge=0)
    risk_level: str = "medium"
    source_type: str = "manual"
    source_id: str = ""


class SOPCreatePayload(BaseModel):
    code: str
    title: str
    body_text: str = ""
    source_reference: str = ""
    required_roles: list[str] = Field(default_factory=list)
    control_rules: list[dict[str, Any]] = Field(default_factory=list)
    facility_specific: bool = False
    activate: bool = False


class SOPDeviationPayload(BaseModel):
    sop_id: str
    entity_type: str
    entity_id: str
    rule_key: str
    severity: str = "medium"
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""


class LabelTemplatePayload(BaseModel):
    name: str
    jurisdiction: str = ""
    license_scope: str = ""
    layout: dict[str, Any] = Field(default_factory=dict)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    facility_specific: bool = False
    activate: bool = False


class LabelReviewPayload(BaseModel):
    label: dict[str, Any]
    template_id: str | None = None
    product_id: str | None = None
    package_id: str = ""
    rules: list[dict[str, Any]] = Field(default_factory=list)
    rule_set_reference: str = ""


class TelemetryPayload(BaseModel):
    machine_id: str
    event_type: str
    metric_key: str = ""
    numeric_value: float | None = None
    unit: str = ""
    state: str = ""
    source: str = "manual"
    external_event_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime | None = None


class HarvestPayload(BaseModel):
    harvest_code: str
    strain: str
    room: str = ""
    plant_count: int = Field(default=0, ge=0)
    wet_weight_g: float = Field(default=0, ge=0)
    dry_weight_g: float = Field(default=0, ge=0)
    waste_weight_g: float = Field(default=0, ge=0)
    labor_hours: float = Field(default=0, ge=0)
    status: str = "planned"
    notes: str = ""
    harvested_at: datetime | None = None


class PortalAccessPayload(BaseModel):
    partner_id: str
    label: str = "Retailer Portal"
    expires_days: int = Field(default=90, ge=1, le=365)


class PortalOrderLine(BaseModel):
    product_id: str
    quantity: float = Field(gt=0)


class PortalOrderPayload(BaseModel):
    lines: list[PortalOrderLine] = Field(min_length=1)
    requested_delivery_date: date | None = None
    purchase_order_reference: str = ""
    notes: str = ""


class ServiceAccountPayload(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)
    facility_specific: bool = False


class WebhookPayload(BaseModel):
    name: str
    target_url: str
    event_types: list[str] = Field(min_length=1)
    facility_specific: bool = False


@router.get("/summary")
def control_summary(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    moat = OperationalMoatService(engine)
    trace = TraceabilityBackofficeRepository(engine).summary(context.organization_id, context.facility_id)
    actions = DoobieActionService(engine).list_proposals(context.organization_id, context.facility_id, limit=500)
    deviations = moat.list_deviations(context.organization_id, context.facility_id)
    labels = moat.list_label_reviews(context.organization_id, context.facility_id, limit=100)
    telemetry = moat.telemetry_summary(context.organization_id, context.facility_id)
    return {"traceability": trace, "actions": {"open": sum(row.status in {"proposed", "approved", "failed"} for row in actions), "proposed": sum(row.status == "proposed" for row in actions), "approved": sum(row.status == "approved" for row in actions), "failed": sum(row.status == "failed" for row in actions)}, "sop": {"open_deviations": len(deviations), "critical": sum(row.severity == "critical" for row in deviations), "high": sum(row.severity == "high" for row in deviations)}, "labels": {"recent_reviews": len(labels), "failures": sum(row.status == "fail" for row in labels), "warnings": sum(row.status == "warning" for row in labels)}, "machines": telemetry, "provider_readiness": {"metrc": "production transaction ledger + approved worker", "biotrack": "provider-neutral ledger; production adapter activation requires provider credentials/certification", "quickbooks": "sandbox sync runtime; production OAuth activation remains credential-gated", "dutchie": "sandbox/live-read bridge supported as interoperability, not system-of-record dependency"}}


@router.get("/traceability")
def traceability_queue(statuses: str = "", provider: str = "", limit: int = Query(default=250, ge=1, le=1000), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    repository = TraceabilityBackofficeRepository(engine)
    rows = repository.list_transactions(context.organization_id, context.facility_id, statuses=tuple(value.strip() for value in statuses.split(",") if value.strip()) or None, provider=provider, limit=limit)
    return {"summary": repository.summary(context.organization_id, context.facility_id), "transactions": [_trace_row(row) for row in rows]}


@router.get("/traceability/{transaction_id}/events")
def traceability_events(transaction_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        rows = TraceabilityBackofficeRepository(engine).list_status_events(context.organization_id, context.facility_id, transaction_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return [_dump(row, ("id", "from_status", "to_status", "actor", "reason", "source", "occurred_at")) for row in rows]


def _trace_action(method: str, transaction_id: str, payload: ReasonPayload, context: RequestContext, engine: Engine):
    _require_role(context, set(MANUAL_TRACEABILITY_ROLES))
    repository = TraceabilityBackofficeRepository(engine)
    try:
        function = getattr(repository, f"{method}_manual")
        row = function(organization_id=context.organization_id, facility_id=context.facility_id, transaction_id=transaction_id, actor=context.user_id, reason=payload.reason)
        return _trace_row(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/traceability/{transaction_id}/requeue")
def requeue_traceability(transaction_id: str, payload: ReasonPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return _trace_action("requeue", transaction_id, payload, context, engine)


@router.post("/traceability/{transaction_id}/verify")
def verify_traceability(transaction_id: str, payload: ReasonPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return _trace_action("verify", transaction_id, payload, context, engine)


@router.post("/traceability/{transaction_id}/cancel")
def cancel_traceability(transaction_id: str, payload: ReasonPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return _trace_action("cancel", transaction_id, payload, context, engine)


@router.get("/actions")
def list_actions(statuses: str = "proposed,approved,failed", context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    wanted = tuple(value.strip() for value in statuses.split(",") if value.strip())
    rows = DoobieActionService(engine).list_proposals(context.organization_id, context.facility_id, statuses=wanted or ("proposed", "approved", "failed"), limit=250)
    return {"allowed_action_types": sorted(ALLOWED_ACTIONS), "actions": [_action_row(row) for row in rows]}


@router.post("/actions")
def propose_action(payload: ActionProposalPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, MUTATION_ROLES)
    if payload.action_type not in ALLOWED_ACTIONS:
        raise HTTPException(422, "Action type is not registered for deterministic execution.")
    try:
        row = DoobieActionService(engine).propose(organization_id=context.organization_id, facility_id=context.facility_id, action_type=payload.action_type, title=payload.title, rationale=payload.rationale, payload=payload.payload, preview=payload.preview, actor=context.user_id, idempotency_key=payload.idempotency_key, financial_impact_usd=payload.financial_impact_usd, risk_level=payload.risk_level, source_type=payload.source_type, source_id=payload.source_id)
        return _action_row(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _find_action(service: DoobieActionService, context: RequestContext, proposal_id: str, statuses: tuple[str, ...]):
    return next((row for row in service.list_proposals(context.organization_id, context.facility_id, statuses=statuses, limit=500) if row.id == proposal_id), None)


def _action_allowed(context: RequestContext, action_type: str) -> None:
    _require_role(context, ACTION_APPROVERS.get(action_type, ADMIN_ROLES), "Your role is not authorized to approve this action type.")


@router.post("/actions/{proposal_id}/approve")
def approve_action(proposal_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    service = DoobieActionService(engine); proposal = _find_action(service, context, proposal_id, ("proposed", "failed"))
    if not proposal:
        raise HTTPException(404, "Action proposal was not found.")
    _action_allowed(context, proposal.action_type)
    try:
        return _action_row(service.approve(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/{proposal_id}/reject")
def reject_action(proposal_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, {"dev", "admin", "buyer", "planner", "supervisor", "qa"})
    try:
        return _action_row(DoobieActionService(engine).reject(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/{proposal_id}/execute")
def execute_action(proposal_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    service = DoobieActionService(engine); proposal = _find_action(service, context, proposal_id, ("approved",))
    if not proposal:
        raise HTTPException(404, "Approved action proposal was not found.")
    _action_allowed(context, proposal.action_type)
    try:
        return service.execute(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/profitability")
def profitability(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return profitability_360(engine, context.organization_id, context.facility_id)


@router.get("/sops")
def list_sops(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    rows = OperationalMoatService(engine).list_sops(context.organization_id, context.facility_id)
    return [_dump(row, ("id", "code", "title", "version", "status", "source_reference", "effective_date", "created_by", "approved_by", "approved_at", "created_at", "updated_at")) | {"required_roles": json.loads(row.required_roles_json or "[]"), "control_rules": json.loads(row.control_rules_json or "[]")} for row in rows]


@router.post("/sops")
def create_sop(payload: SOPCreatePayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, ADMIN_ROLES | {"qa"})
    try:
        row = OperationalMoatService(engine).create_sop(organization_id=context.organization_id, facility_id=context.facility_id if payload.facility_specific else None, code=payload.code, title=payload.title, body_text=payload.body_text, actor=context.user_id, source_reference=payload.source_reference, required_roles=payload.required_roles, control_rules=payload.control_rules, activate=payload.activate)
        return _dump(row, ("id", "code", "title", "version", "status", "effective_date"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/sops/{sop_id}/activate")
def activate_sop(sop_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, ADMIN_ROLES | {"qa"})
    try:
        row = OperationalMoatService(engine).activate_sop(context.organization_id, sop_id, context.user_id)
        return _dump(row, ("id", "code", "version", "status", "effective_date", "approved_by", "approved_at"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/sops/{sop_id}/acknowledge")
def acknowledge_sop(sop_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try:
        row = OperationalMoatService(engine).acknowledge_sop(context.organization_id, context.facility_id, sop_id, context.user_id)
        return _dump(row, ("id", "sop_document_id", "user_id", "acknowledged_at"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sop-deviations")
def deviations(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    rows = OperationalMoatService(engine).list_deviations(context.organization_id, context.facility_id)
    return [_dump(row, ("id", "sop_document_id", "entity_type", "entity_id", "rule_key", "severity", "status", "explanation", "detected_at", "detected_by")) | {"evidence": json.loads(row.evidence_json or "{}")} for row in rows]


@router.post("/sop-deviations")
def create_deviation(payload: SOPDeviationPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, COMPLIANCE_ROLES)
    try:
        row = OperationalMoatService(engine).record_deviation(organization_id=context.organization_id, facility_id=context.facility_id, sop_id=payload.sop_id, entity_type=payload.entity_type, entity_id=payload.entity_id, rule_key=payload.rule_key, severity=payload.severity, evidence=payload.evidence, explanation=payload.explanation, actor=context.user_id)
        return _dump(row, ("id", "severity", "status", "detected_at"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/label-templates")
def label_templates(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    rows = OperationalMoatService(engine).list_label_templates(context.organization_id, context.facility_id)
    return [_dump(row, ("id", "name", "version", "jurisdiction", "license_scope", "status", "approved_by", "approved_at")) | {"layout": json.loads(row.layout_json or "{}"), "rules": json.loads(row.rules_json or "[]")} for row in rows]


@router.post("/label-templates")
def create_label_template(payload: LabelTemplatePayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, ADMIN_ROLES | {"qa"})
    try:
        row = OperationalMoatService(engine).create_label_template(organization_id=context.organization_id, facility_id=context.facility_id if payload.facility_specific else None, name=payload.name, jurisdiction=payload.jurisdiction, license_scope=payload.license_scope, layout=payload.layout, rules=payload.rules, actor=context.user_id, activate=payload.activate)
        return _dump(row, ("id", "name", "version", "status", "jurisdiction", "license_scope"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/label-reviews")
def review_label(payload: LabelReviewPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, COMPLIANCE_ROLES | {"operator"})
    try:
        row, findings = OperationalMoatService(engine).review_label(organization_id=context.organization_id, facility_id=context.facility_id, label=payload.label, actor=context.user_id, template_id=payload.template_id, product_id=payload.product_id, package_id=payload.package_id, ad_hoc_rules=payload.rules, rule_set_reference=payload.rule_set_reference)
        return {"id": row.id, "status": row.status, "reviewed_at": row.reviewed_at, "findings": findings, "disclaimer": "Deterministic review against the selected, reviewed rule set. Confirm current law and approved SOP before release."}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/machine-telemetry")
def machine_telemetry(hours: int = Query(default=24, ge=1, le=720), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return OperationalMoatService(engine).telemetry_summary(context.organization_id, context.facility_id, hours)


@router.post("/machine-telemetry")
def record_machine_telemetry(payload: TelemetryPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_facility_capability(context, engine, "production"); _require_role(context, MUTATION_ROLES)
    try:
        row = OperationalMoatService(engine).record_telemetry(organization_id=context.organization_id, facility_id=context.facility_id, machine_id=payload.machine_id, event_type=payload.event_type, actor=context.user_id, metric_key=payload.metric_key, numeric_value=payload.numeric_value, unit=payload.unit, state=payload.state, source=payload.source, external_event_id=payload.external_event_id, payload=payload.payload, recorded_at=payload.recorded_at)
        return _dump(row, ("id", "machine_id", "event_type", "metric_key", "numeric_value", "unit", "state", "recorded_at"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/cultivation/harvests")
def cultivation_harvests(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_facility_capability(context, engine, "cultivation"); service = OperationalMoatService(engine); rows = service.list_harvests(context.organization_id, context.facility_id)
    return {"summary": service.harvest_summary(context.organization_id, context.facility_id), "harvests": [_dump(row, ("id", "harvest_code", "strain", "room", "plant_count", "wet_weight_g", "dry_weight_g", "waste_weight_g", "labor_hours", "status", "harvested_at", "completed_at", "notes")) for row in rows]}


@router.post("/cultivation/harvests")
def create_cultivation_harvest(payload: HarvestPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_facility_capability(context, engine, "cultivation"); _require_role(context, MUTATION_ROLES)
    try:
        row = OperationalMoatService(engine).create_harvest(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return _dump(row, ("id", "harvest_code", "strain", "status", "wet_weight_g", "dry_weight_g", "created_at"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/commerce/access")
def issue_commerce_access(payload: PortalAccessPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    require_facility_capability(context, engine, "commercial"); _require_role(context, ADMIN_ROLES | {"supervisor"})
    try:
        row, token = OperationalMoatService(engine).issue_partner_portal_access(organization_id=context.organization_id, facility_id=context.facility_id, partner_id=payload.partner_id, actor=context.user_id, label=payload.label, expires_days=payload.expires_days)
        return {"id": row.id, "token": token, "expires_at": row.expires_at, "warning": "This token is shown once. Store it securely."}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/enterprise/service-accounts")
def issue_service_account(payload: ServiceAccountPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, ADMIN_ROLES)
    try:
        row, token = OperationalMoatService(engine).issue_service_account(organization_id=context.organization_id, facility_id=context.facility_id if payload.facility_specific else None, name=payload.name, scopes=payload.scopes, actor=context.user_id)
        return {"id": row.id, "name": row.name, "token": token, "scopes": json.loads(row.scopes_json), "warning": "This token is shown once. Store it securely."}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/enterprise/webhooks")
def create_webhook(payload: WebhookPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_role(context, ADMIN_ROLES)
    try:
        row, secret = OperationalMoatService(engine).create_webhook(organization_id=context.organization_id, facility_id=context.facility_id if payload.facility_specific else None, name=payload.name, target_url=payload.target_url, event_types=payload.event_types, actor=context.user_id)
        return {"id": row.id, "name": row.name, "target_url": row.target_url, "secret": secret, "event_types": json.loads(row.event_types_json), "warning": "The signing secret is shown once. Delivery remains queued until a webhook worker is configured."}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@public_router.get("/{token}")
def commerce_portal(token: str, engine: Engine = Depends(get_engine)):
    try:
        service = OperationalMoatService(engine); access = service.resolve_partner_portal(token); return service.partner_catalog(access)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@public_router.post("/{token}/orders")
def create_portal_order(token: str, payload: PortalOrderPayload, engine: Engine = Depends(get_engine)):
    service = OperationalMoatService(engine)
    try:
        access = service.resolve_partner_portal(token); catalog = service.partner_catalog(access); by_product = {row["product_id"]: row for row in catalog["catalog"]}; lines = []
        for requested in payload.lines:
            item = by_product.get(requested.product_id)
            if not item:
                raise ValueError("Requested product is not currently available to this partner.")
            if requested.quantity > float(item["available"]):
                raise ValueError(f"Requested quantity exceeds available inventory for {item['name']}.")
            lines.append({"product_id": requested.product_id, "quantity": requested.quantity, "unit": item["unit"], "unit_price": item["price_usd"], "description": item["name"]})
        order_number = f"PORTAL-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{access.id[:6].upper()}"
        order = CommercialRepository(engine).create_order(organization_id=access.organization_id, facility_id=access.facility_id, partner_id=access.partner_id, order_number=order_number, order_type="sales", order_date=date.today(), due_date=payload.requested_delivery_date, lines=lines, actor=f"portal:{access.id}", external_reference=payload.purchase_order_reference, notes=payload.notes or "Created through DoobieCommerce retailer portal.")
        service.queue_webhook_event(organization_id=access.organization_id, facility_id=access.facility_id, event_type="commercial.order.created", event_id=order.id, payload={"order_id": order.id, "order_number": order.order_number, "source": "partner_portal"})
        return {"order_id": order.id, "order_number": order.order_number, "status": order.status}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
