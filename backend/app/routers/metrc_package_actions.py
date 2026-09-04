from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import LIFECYCLE_EVALUATION_ACTIONS

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..config import Settings, get_settings
from ..database import get_engine
from ..services.metrc_package_actions import (
    MetrcPackageActionError,
    PROMOTED_PACKAGE_ACTIONS,
    package_confirmation_token,
)
from ..services.metrc_package_identity import MetrcPackageIdentityError, MetrcPackageIdentityService
from ..services.metrc_package_operator_service import GovernedMetrcPackageActionService
from ..services.metrc_package_reference import MetrcPackageReferenceError, fetch_package_adjustment_reasons
from ..services.regulatory_metrc import resolve_trusted_regulatory_metrc


router = APIRouter(prefix="/metrc-packages", tags=["metrc-packages"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator", "qa", "planner"}


def _write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow controlled package traceability changes.")


def _resolved(context: RequestContext, engine: Engine, settings: Settings):
    require_facility_capability(context, engine, "production")
    return resolve_trusted_regulatory_metrc(
        context=context,
        engine=engine,
        settings=settings,
        facility_capability="production",
    )


def _metrc(context: RequestContext, engine: Engine, settings: Settings):
    metrc = _resolved(context, engine, settings)
    if not metrc.configured:
        raise HTTPException(409, metrc.message)
    if str(metrc.state or "").strip().upper() != "MA" or str(metrc.environment or "").strip().casefold() != "sandbox":
        raise HTTPException(409, "Promoted package writes are currently restricted to the verified Massachusetts Metrc sandbox.")
    return metrc


def _bounded_resource(metrc, resource: str, *, max_pages: int = 20, page_size: int = 50) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for page_number in range(1, max_pages + 1):
        result = fetch_metrc_resource(
            state=metrc.state,
            user_api_key=metrc.user_api_key,
            integrator_api_key=metrc.integrator_api_key,
            resource=resource,
            environment=metrc.environment,
            license_number=metrc.license_number,
            page_size=page_size,
            page_number=page_number,
        )
        if not result.get("ok"):
            raise HTTPException(502, str(result.get("message") or f"Metrc {resource} lookup failed."))
        page = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
        rows.extend(page)
        if len(page) < page_size:
            return {"records": rows, "truncated": False, "page_size": page_size, "max_pages": max_pages}
    return {"records": rows, "truncated": True, "page_size": page_size, "max_pages": max_pages}


class ProductLinkRequest(BaseModel):
    provider_item_id: str = Field(min_length=1, max_length=64)


class LotLinkRequest(BaseModel):
    provider_package_id: str = Field(min_length=1, max_length=64)


class PackageActionRequest(BaseModel):
    operation_type: Literal["package_adjust", "package_item", "package_finish", "package_unfinish"]
    lot_id: str = Field(min_length=1, max_length=64)
    actual_date: date = Field(default_factory=date.today)
    quantity_delta: float = 0.0
    adjustment_reason: str = Field(default="", max_length=160)
    reason_note: str = Field(default="", max_length=255)
    target_product_id: str = Field(default="", max_length=64)
    reason: str = Field(default="Package Metrc synchronization", min_length=3, max_length=255)


class PackageActionExecute(PackageActionRequest):
    confirmation_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=32, max_length=128)


def _kwargs(payload: PackageActionRequest) -> dict[str, Any]:
    return {
        "operation_type": payload.operation_type,
        "lot_id": payload.lot_id,
        "actual_date": payload.actual_date.isoformat(),
        "quantity_delta": payload.quantity_delta,
        "adjustment_reason": payload.adjustment_reason,
        "reason_note": payload.reason_note,
        "target_product_id": payload.target_product_id,
        "reason": payload.reason,
    }


@router.get("/status")
def package_status(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _resolved(context, engine, settings)
    jurisdiction = str(metrc.state or "").strip().upper()
    environment = str(metrc.environment or "").strip().casefold()
    ready = bool(metrc.configured and jurisdiction == "MA" and environment == "sandbox")
    return {
        "ready": ready,
        "provider": "metrc",
        "jurisdiction_code": jurisdiction,
        "environment": environment,
        "license_number": str(metrc.license_number or "").strip(),
        "promoted_actions": sorted(PROMOTED_PACKAGE_ACTIONS) if ready else [],
        "message": "Verified Massachusetts Metrc sandbox package checkpoints are available." if ready else str(metrc.message or "This facility remains on the local-only package workflow."),
        "execution_boundary": "Every write requires exact Product↔Item and Inventory Lot↔Package identities plus fresh local/provider equality before preview and again before execution." if ready else "Local package workflows remain available; promoted provider writes stay disabled.",
    }


@router.get("/identities")
def identities(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    return {
        "environment": metrc.environment,
        "license_number": metrc.license_number,
        **MetrcPackageIdentityService(engine).list_links(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            environment=metrc.environment,
        ),
    }


@router.get("/items")
def active_items(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    result = _bounded_resource(metrc, "items_active")
    return {
        "items": [{"provider_id": str(row.get("provider_id") or ""), "name": str(row.get("name") or ""), "last_modified": str(row.get("last_modified") or "")} for row in result["records"] if str(row.get("provider_id") or "").strip()],
        **{key: result[key] for key in ("truncated", "page_size", "max_pages")},
    }


@router.get("/packages")
def active_packages(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    result = _bounded_resource(metrc, "packages_active")
    return {
        "items": [{
            "provider_id": str(row.get("provider_id") or ""), "label": str(row.get("label") or ""),
            "name": str(row.get("name") or ""), "quantity": row.get("quantity"),
            "unit_of_measure": str(row.get("unit_of_measure") or ""), "last_modified": str(row.get("last_modified") or ""),
        } for row in result["records"] if str(row.get("provider_id") or "").strip()],
        **{key: result[key] for key in ("truncated", "page_size", "max_pages")},
    }


@router.get("/available-tags")
def available_package_tags(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    result = _bounded_resource(metrc, "package_tags_available", max_pages=20, page_size=50)
    labels = []
    seen = set()
    for row in result["records"]:
        label = str(row.get("label") or row.get("name") or "").strip()
        key = label.casefold()
        if label and key not in seen:
            labels.append(label)
            seen.add(key)
    return {"items": labels, **{key: result[key] for key in ("truncated", "page_size", "max_pages")}}


@router.get("/adjustment-reasons")
def adjustment_reasons(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    metrc = _metrc(context, engine, settings)
    try:
        return fetch_package_adjustment_reasons(
            state=metrc.state,
            environment=metrc.environment,
            integrator_api_key=metrc.integrator_api_key,
            user_api_key=metrc.user_api_key,
        )
    except MetrcPackageReferenceError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/products/{product_id}/link")
def link_product(
    product_id: str,
    payload: ProductLinkRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        return MetrcPackageIdentityService(engine).link_product(
            organization_id=context.organization_id, facility_id=context.facility_id,
            product_id=product_id, provider_item_id=payload.provider_item_id,
            state=metrc.state, environment=metrc.environment, license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key, user_api_key=metrc.user_api_key,
        )
    except MetrcPackageIdentityError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/lots/{lot_id}/link")
def link_lot(
    lot_id: str,
    payload: LotLinkRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        return MetrcPackageIdentityService(engine).link_lot(
            organization_id=context.organization_id, facility_id=context.facility_id,
            lot_id=lot_id, provider_package_id=payload.provider_package_id,
            state=metrc.state, environment=metrc.environment, license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key, user_api_key=metrc.user_api_key,
        )
    except MetrcPackageIdentityError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/preview")
def preview_package_action(
    payload: PackageActionRequest,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    service = GovernedMetrcPackageActionService(engine)
    try:
        prepared = service.prepare(
            organization_id=context.organization_id, facility_id=context.facility_id,
            state=metrc.state, environment=metrc.environment, license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key, user_api_key=metrc.user_api_key,
            **_kwargs(payload),
        )
        confirmation_id = str(uuid4())
        token = package_confirmation_token(
            prepared=prepared, state=metrc.state, environment=metrc.environment,
            license_number=metrc.license_number, confirmation_id=confirmation_id,
        )
        spec = LIFECYCLE_EVALUATION_ACTIONS[prepared["evaluator_operation"]]
        return {
            "ready": True, "operation_type": prepared["operation_type"], "summary": prepared["summary"],
            "confirmation_id": confirmation_id, "confirmation_token": token,
            "compliance_evidence": {
                "method": spec.method, "path": spec.path, "license_number": metrc.license_number,
                "environment": metrc.environment, "provider_request_body": prepared["provider_request_body"], "provider_atomic": True,
            },
            "message": "Review the package business values before confirming. Any local ledger, identity, or Metrc state change invalidates this confirmation.",
        }
    except MetrcPackageActionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/actions/execute")
def execute_package_action(
    payload: PackageActionExecute,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
):
    _write(context)
    metrc = _metrc(context, engine, settings)
    try:
        return GovernedMetrcPackageActionService(engine).execute(
            organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id,
            state=metrc.state, environment=metrc.environment, license_number=metrc.license_number,
            integrator_api_key=metrc.integrator_api_key, user_api_key=metrc.user_api_key,
            confirmation_id=payload.confirmation_id, confirmation_token=payload.confirmation_token,
            **_kwargs(payload),
        )
    except MetrcPackageActionError as exc:
        raise HTTPException(422, str(exc)) from exc
