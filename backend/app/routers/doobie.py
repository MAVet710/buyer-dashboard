import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.doobie_actions.service import ALLOWED_ACTIONS, DoobieActionService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.traceability_dispatcher import TraceabilityDispatchError, TraceabilityDispatcher
from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.manifest_drafts import ManifestDraftService
from ..services.manifest_lifecycle import ManifestLifecycleError, ManifestLifecycleService
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc

router = APIRouter(prefix="/doobie", tags=["doobie"])
APPROVAL_ROLES = {"dev", "admin", "supervisor"}


class ProposalCreate(BaseModel):
    action_type: str
    title: str
    rationale: str = ""
    payload: dict = Field(default_factory=dict)
    preview: dict = Field(default_factory=dict)
    financial_impact_usd: float = 0
    risk_level: str = "medium"
    idempotency_key: str = ""


class ManifestDraftCreate(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    estimated_departure: str = Field(min_length=1, max_length=80)
    estimated_arrival: str = Field(min_length=1, max_length=80)
    planned_route: str = Field(min_length=1, max_length=2000)
    transfer_type_name: str = Field(default="Transfer", min_length=1, max_length=160)
    transporter_facility_license_number: str = Field(default="", max_length=255)
    driver_name: str = Field(default="", max_length=255)
    driver_license_number: str = Field(default="", max_length=255)
    driver_occupational_license_number: str = Field(default="", max_length=255)
    phone_number_for_questions: str = Field(default="", max_length=80)
    vehicle_license_plate_number: str = Field(default="", max_length=80)
    vehicle_make: str = Field(default="", max_length=120)
    vehicle_model: str = Field(default="", max_length=120)


def _item(row):
    return {key: getattr(row, key) for key in ("id", "action_type", "title", "rationale", "financial_impact_usd", "risk_level", "status", "source_type", "source_id", "created_by", "approved_by", "approved_at", "expires_at", "created_at")} | {"payload": json.loads(row.payload_json or "{}"), "preview": json.loads(row.preview_json or "{}")}


@router.get("/actions")
def actions(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    return {"allowed_actions": sorted(ALLOWED_ACTIONS), "items": [_item(row) for row in DoobieActionService(engine).list_proposals(context.organization_id, context.facility_id, statuses=("proposed", "approved", "executing", "executed", "rejected", "failed", "expired"))]}


@router.post("/actions", status_code=201)
def propose(payload: ProposalCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if payload.action_type == "prepare_transfer_manifest":
        raise HTTPException(422, "Transfer manifest drafts must be created through the governed Wholesale Ops manifest builder.")
    try:
        return _item(DoobieActionService(engine).propose(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, idempotency_key=payload.idempotency_key or f"web:{uuid4()}", source_type="web", **payload.model_dump(exclude={"idempotency_key"})))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/{proposal_id}/{action}")
def decide(proposal_id: str, action: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    if context.role.casefold() not in APPROVAL_ROLES:
        raise HTTPException(403, "Your role cannot approve or execute Doobie actions.")
    service = DoobieActionService(engine)
    try:
        if action == "approve":
            return _item(service.approve(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id))
        if action == "reject":
            return _item(service.reject(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id))
        if action == "execute":
            return service.execute(organization_id=context.organization_id, facility_id=context.facility_id, proposal_id=proposal_id, actor=context.user_id)
        raise HTTPException(404, "Unsupported Doobie action decision.")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/manifest-drafts/candidates")
def manifest_candidates(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    require_facility_capability(context, engine, "commercial")
    return {"items": ManifestDraftService(engine).candidates(context.organization_id, context.facility_id)}


@router.post("/manifest-drafts", status_code=201)
def build_manifest_draft(
    payload: ManifestDraftCreate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    require_facility_capability(context, engine, "commercial")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="commercial",
    )
    if not metrc.configured:
        raise HTTPException(409, "Connect and validate the Massachusetts Metrc sandbox for this facility before building a provider-ready manifest draft.")
    if metrc.state.upper() != "MA" or metrc.environment != "sandbox":
        raise HTTPException(409, "This first controlled manifest-write phase requires the Massachusetts Metrc sandbox.")
    try:
        row = ManifestDraftService(engine).build_proposal(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
            license_number=metrc.license_number,
            jurisdiction_code=metrc.state,
            environment=metrc.environment,
            **payload.model_dump(),
        )
        return _item(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/manifest-drafts/{proposal_id}/submit")
def submit_manifest_draft(
    proposal_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    if context.role.casefold() not in APPROVAL_ROLES:
        raise HTTPException(403, "Your role cannot submit approved regulatory actions.")
    require_facility_capability(context, engine, "commercial")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="commercial",
    )
    if not metrc.configured or metrc.state.upper() != "MA" or metrc.environment != "sandbox":
        raise HTTPException(409, "Manifest submission is currently enabled only through the trusted Massachusetts Metrc sandbox mapping.")

    service = DoobieActionService(engine)
    proposal = next((row for row in service.list_proposals(context.organization_id, context.facility_id, statuses=("proposed", "approved", "executing", "executed", "failed", "rejected", "expired"), limit=500) if row.id == proposal_id), None)
    if proposal is None or proposal.action_type != "prepare_transfer_manifest":
        raise HTTPException(404, "Manifest draft was not found in the active facility.")
    if proposal.status not in {"approved", "executed"}:
        raise HTTPException(422, "An authorized employee must approve the manifest preview before submission.")
    try:
        execution = service.execute(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            proposal_id=proposal.id,
            actor=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    transaction_id = str(execution.get("transaction_id") or "")
    if not transaction_id:
        raise HTTPException(409, "The approved manifest draft did not produce a traceability transaction.")

    traceability = TraceabilityBackofficeRepository(engine)
    transaction = traceability.get_transaction(context.organization_id, context.facility_id, transaction_id)
    if transaction.status in {"accepted", "verified"}:
        return {
            "proposal_id": proposal.id,
            "transaction_id": transaction.id,
            "status": transaction.status,
            "provider": "metrc",
            "environment": metrc.environment,
            "already_submitted": True,
            "external_reference": transaction.external_reference,
        }
    if transaction.status != "queued":
        raise HTTPException(409, f"Manifest traceability transaction is {transaction.status}; reconcile it before another submission attempt.")

    try:
        dispatch = TraceabilityDispatcher(
            engine,
            encryption_key=settings.integration_encryption_key,
            metrc_integrator_api_key=settings.metrc_integrator_key,
        ).dispatch(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            transaction_id=transaction.id,
            actor=context.user_id,
        )
    except TraceabilityDispatchError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "proposal_id": proposal.id,
        "transaction_id": transaction.id,
        "provider": "metrc",
        "jurisdiction_code": "MA",
        "environment": "sandbox",
        "dispatch": dispatch,
        "message": "The authorized employee submitted the approved outgoing transfer template to the Massachusetts Metrc sandbox. Final manifest issuance remains a separate Metrc state that DoobieLogic must verify.",
    }


@router.get("/manifest-drafts/{proposal_id}/lifecycle")
def manifest_lifecycle(
    proposal_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    require_facility_capability(context, engine, "commercial")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="commercial",
    )
    if not metrc.configured or metrc.state.upper() != "MA" or metrc.environment != "sandbox":
        raise HTTPException(409, "Manifest lifecycle verification is currently enabled only through the trusted Massachusetts Metrc sandbox mapping.")
    try:
        return ManifestLifecycleService(engine).inspect(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            proposal_id=proposal_id,
            actor=context.user_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
        )
    except ManifestLifecycleError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/manifest-drafts/{proposal_id}/manifest.pdf")
def manifest_pdf(
    proposal_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    require_facility_capability(context, engine, "commercial")
    metrc = resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="commercial",
    )
    if not metrc.configured or metrc.state.upper() != "MA" or metrc.environment != "sandbox":
        raise HTTPException(409, "Manifest PDF retrieval is currently enabled only through the trusted Massachusetts Metrc sandbox mapping.")
    try:
        content, manifest_number = ManifestLifecycleService(engine).manifest_pdf(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            proposal_id=proposal_id,
            actor=context.user_id,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
        )
    except ManifestLifecycleError as exc:
        raise HTTPException(409, str(exc)) from exc
    safe_name = "".join(character for character in manifest_number if character.isalnum() or character in {"-", "_"}) or "metrc-manifest"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )
