from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Engine

from modules.legal_acceptance.policies import CURRENT_PRIVACY_POLICY, CURRENT_TERMS_POLICY, PRIVACY_TEXT, STATEMENT_VERSION, TERMS_TEXT
from services.legal_acceptance_store import LegalAcceptanceStore
from ..auth import RequestContext, get_request_context
from ..config import Settings, get_settings
from ..database import get_engine

router = APIRouter(prefix="/legal", tags=["legal"])


class AcceptanceCreate(BaseModel):
    accepted: bool


def _environment(settings: Settings) -> str:
    value = settings.app_env.casefold()
    return "sandbox" if value in {"development", "dev", "test", "sandbox"} else "trial" if value == "trial" else "production"


@router.get("/current")
def current_policies(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    store = LegalAcceptanceStore(engine=engine)
    if not store.available(): raise HTTPException(503, "The current agreement is temporarily unavailable. Access remains paused.")
    accepted = store.has_accepted(user_id=context.user_id, terms_version=CURRENT_TERMS_POLICY.version, privacy_version=CURRENT_PRIVACY_POLICY.version)
    return {"accepted": accepted, "terms": {"version": CURRENT_TERMS_POLICY.version, "effective_at": CURRENT_TERMS_POLICY.effective_at, "text": TERMS_TEXT, "sha256": CURRENT_TERMS_POLICY.document_sha256}, "privacy": {"version": CURRENT_PRIVACY_POLICY.version, "effective_at": CURRENT_PRIVACY_POLICY.effective_at, "text": PRIVACY_TEXT, "sha256": CURRENT_PRIVACY_POLICY.document_sha256}, "statement_version": STATEMENT_VERSION, "statement": "I have read and agree to the Terms of Service and acknowledge the Privacy Policy. I confirm that I am at least 21 years old and authorized to use DoobieLogic for my organization."}


@router.post("/accept", status_code=201)
def accept_policies(payload: AcceptanceCreate, request: Request, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    if payload.accepted is not True: raise HTTPException(422, "Review and accept the Terms of Service and Privacy Policy to continue.")
    forwarded = request.headers.get("X-Forwarded-For", ""); ip_address = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "")
    try:
        row = LegalAcceptanceStore(engine=engine).record_acceptance(user_id=context.user_id, organization_id=context.organization_id, terms=CURRENT_TERMS_POLICY, privacy=CURRENT_PRIVACY_POLICY, statement_version=STATEMENT_VERSION, acceptance_method="first_login", environment=_environment(settings), ip_address=ip_address, user_agent=request.headers.get("User-Agent", ""))
        return {"id": row.id, "accepted_at": row.accepted_at, "terms_version": row.terms_version, "privacy_version": row.privacy_version}
    except (RuntimeError, ValueError) as exc: raise HTTPException(503, "We could not securely record your acceptance. Your account has not been changed.") from exc
