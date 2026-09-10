from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.metrc_evaluation_sales import SALES_EVALUATION_ACTIONS

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_sales_actions import (
    GovernedMetrcSalesActionService,
    MetrcSalesActionError,
    PROMOTED_SALES_ACTIONS,
    sales_confirmation_token,
)
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc


router = APIRouter(prefix="/metrc-sales", tags=["metrc-sales"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa"}
SalesOperation = Literal[
    "sales_receipt_create",
    "sales_receipt_update",
    "sales_receipt_delete",
    "sales_delivery_create",
    "sales_delivery_update",
    "sales_delivery_complete",
]


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow controlled Metrc sales changes.")


def _resolved(context: RequestContext, engine: Engine, settings: Settings):
    require_facility_capability(context, engine, "retail")
    return resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="retail",
    )


def _metrc(context: RequestContext, engine: Engine, settings: Settings):
    metrc = _resolved(context, engine, settings)
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    if str(metrc.state or "").strip().upper() != "MA" or str(metrc.environment or "").strip().casefold() != "sandbox":
        raise HTTPException(
            409,
            "Promoted sales writes are currently restricted to the verified Massachusetts Metrc sandbox.",
        )
    return metrc


class SalesActionRequest(BaseModel):
    operation_type: SalesOperation
    payload: dict[str, Any]
    reason: str = Field(default="Controlled Metrc sales action", min_length=3, max_length=255)


class SalesActionExecute(SalesActionRequest):
    confirmation_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=32, max_length=128)


@router.get("/status")
def sales_status(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _resolved(context, engine, settings)
    jurisdiction = str(metrc.state or "").strip().upper()
    environment = str(metrc.environment or "").strip().casefold()
    ready = bool(metrc.configured and metrc.trusted_mapping and jurisdiction == "MA" and environment == "sandbox")
    return {
        "ready": ready,
        "provider": "metrc",
        "jurisdiction_code": jurisdiction,
        "environment": environment,
        "license_number": str(metrc.license_number or "").strip(),
        "promoted_actions": sorted(PROMOTED_SALES_ACTIONS) if ready else [],
        "documentation_source": "https://api-ma.metrc.com/Documentation",
        "execution_host": "sandbox-api-ma.metrc.com" if ready else "",
        "message": (
            "Current Massachusetts Metrc v2 sales contracts are available through the governed sandbox workflow."
            if ready
            else str(metrc.message or "This facility remains on its current local sales workflow.")
        ),
        "execution_boundary": (
            "Every provider write is exact-license scoped, human confirmed, idempotent in the global ledger, and requires fresh exact Metrc readback before verification."
            if ready
            else "Local sales workflows remain available; provider writes stay disabled."
        ),
    }


@router.post("/actions/preview")
def preview_sales_action(
    payload: SalesActionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    service = GovernedMetrcSalesActionService(engine)
    try:
        prepared = service.prepare(
            operation_type=payload.operation_type,
            payload=payload.payload,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
        )
        confirmation_id = str(uuid4())
        token = sales_confirmation_token(
            prepared=prepared,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            confirmation_id=confirmation_id,
        )
        spec = SALES_EVALUATION_ACTIONS[prepared["operation_type"]]
        return {
            "ready": True,
            "operation_type": prepared["operation_type"],
            "summary": prepared["summary"],
            "confirmation_id": confirmation_id,
            "confirmation_token": token,
            "compliance_evidence": {
                "method": spec.method,
                "path": spec.path,
                "license_number": metrc.license_number,
                "environment": metrc.environment,
                "provider_request_body": prepared["provider_request_body"],
                "documentation_source": "https://api-ma.metrc.com/Documentation",
            },
            "message": "Review the business values before confirming. Any payload or facility-context change invalidates this confirmation.",
        }
    except MetrcSalesActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/execute")
def execute_sales_action(
    payload: SalesActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        return GovernedMetrcSalesActionService(engine).execute(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            actor=context.user_id,
            operation_type=payload.operation_type,
            payload=payload.payload,
            confirmation_id=payload.confirmation_id,
            confirmation_token=payload.confirmation_token,
            reason=payload.reason,
            state=metrc.state,
            environment=metrc.environment,
            license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
        )
    except MetrcSalesActionError as exc:
        raise HTTPException(422, str(exc)) from exc
