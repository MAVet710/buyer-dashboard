"""Private supplier offer intake and buyer review surfaces.

This router exposes staged purchasing data only. Supplier submissions never call
inventory, receiving, purchase-order, or traceability mutation services.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.supplier_portal.service import DEFAULT_SUPPLIER_PERMISSIONS, SupplierPortalService

from ..auth import RequestContext, get_request_context
from ..database import get_engine


router = APIRouter(prefix="/supplier-portal", tags=["supplier-portal"])
public_router = APIRouter(prefix="/commerce-portal", tags=["commerce-portal-supplier"])
BUYER_ROLES = {"dev", "admin", "buyer"}


def _require_buyer(context: RequestContext) -> None:
    if context.role.casefold() not in BUYER_ROLES:
        raise HTTPException(403, "Your role does not allow supplier offer review or portal access management.")


class SupplierAccessPayload(BaseModel):
    partner_id: str = Field(min_length=1, max_length=36)
    label: str = Field(default="Supplier Portal", min_length=1, max_length=255)
    expires_days: int = Field(default=90, ge=1, le=365)
    permissions: list[str] | None = None


class SupplierOfferLinePayload(BaseModel):
    product_id: str | None = None
    supplier_sku: str = Field(default="", max_length=160)
    product_name: str = Field(min_length=1, max_length=255)
    strain: str = Field(default="", max_length=255)
    form: str = Field(default="", max_length=160)
    package_size: float | None = Field(default=None, ge=0)
    package_size_unit: str = Field(default="", max_length=40)
    available_quantity: float = Field(default=0, ge=0)
    availability_unit: str = Field(default="unit", min_length=1, max_length=40)
    unit_price: float = Field(default=0, ge=0)
    price_basis: str = Field(default="unit", min_length=1, max_length=40)
    minimum_order_quantity: float = Field(default=0, ge=0)
    minimum_order_unit: str = Field(default="unit", min_length=1, max_length=40)
    batch_lot_identifier: str = Field(default="", max_length=255)
    coa_reference: str = Field(default="", max_length=1024)
    sample_status: str = Field(default="none", max_length=24)
    promotion_terms: str = ""
    notes: str = ""


class SupplierOfferPayload(BaseModel):
    lines: list[SupplierOfferLinePayload] = Field(min_length=1, max_length=500)
    external_reference: str = Field(default="", max_length=255)
    valid_from: date | None = None
    valid_until: date | None = None
    promotion_terms: str = ""
    notes: str = ""
    lead_time_days: int | None = Field(default=None, ge=0, le=365)


class SupplierReviewPayload(BaseModel):
    status: str = Field(pattern="^(under_review|accepted|rejected)$")


def _line_payload(row: Any) -> dict[str, Any]:
    return {
        field: getattr(row, field)
        for field in (
            "id",
            "offer_id",
            "position",
            "product_id",
            "supplier_sku",
            "product_name",
            "strain",
            "form",
            "package_size",
            "package_size_unit",
            "available_quantity",
            "availability_unit",
            "unit_price",
            "price_basis",
            "minimum_order_quantity",
            "minimum_order_unit",
            "batch_lot_identifier",
            "coa_reference",
            "sample_status",
            "promotion_terms",
            "notes",
            "created_at",
        )
    }


def _offer_payload(service: SupplierPortalService, row: Any) -> dict[str, Any]:
    payload = {
        field: getattr(row, field)
        for field in (
            "id",
            "offer_group_id",
            "revision",
            "supersedes_offer_id",
            "organization_id",
            "facility_id",
            "partner_id",
            "status",
            "external_reference",
            "valid_from",
            "valid_until",
            "promotion_terms",
            "notes",
            "lead_time_days",
            "submitted_at",
            "submitted_by",
            "withdrawn_at",
            "created_at",
            "updated_at",
        )
    }
    payload["lines"] = [_line_payload(line) for line in service.list_offer_lines(row.organization_id, row.id)]
    return payload


def _supplier_access(service: SupplierPortalService, token: str, permission: str):
    try:
        return service.resolve_supplier_access(token, permission=permission)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/access", status_code=201)
def issue_supplier_access(
    payload: SupplierAccessPayload,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_buyer(context)
    service = SupplierPortalService(engine)
    try:
        access, grant, token = service.issue_supplier_access(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            partner_id=payload.partner_id,
            actor=context.user_id,
            label=payload.label,
            expires_days=payload.expires_days,
            permissions=payload.permissions or DEFAULT_SUPPLIER_PERMISSIONS,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "access_id": access.id,
        "partner_id": access.partner_id,
        "facility_id": access.facility_id,
        "label": access.label,
        "expires_at": access.expires_at,
        "permissions": sorted(payload.permissions or DEFAULT_SUPPLIER_PERMISSIONS),
        "token": token,
        "warning": "This supplier portal token is shown once. Store and transmit it as a secret.",
        "grant_id": grant.id,
    }


@router.get("/offers")
def buyer_supplier_offers(
    partner_id: str = "",
    current_only: bool = False,
    limit: int = Query(default=250, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_buyer(context)
    service = SupplierPortalService(engine)
    rows = service.list_offers(
        context.organization_id,
        context.facility_id,
        partner_id=partner_id,
        current_only=current_only,
        limit=limit,
    )
    return [_offer_payload(service, row) for row in rows]


@router.post("/offers/{offer_id}/review")
def review_supplier_offer(
    offer_id: str,
    payload: SupplierReviewPayload,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _require_buyer(context)
    service = SupplierPortalService(engine)
    try:
        row = service.review_offer(
            organization_id=context.organization_id,
            facility_id=context.facility_id,
            offer_id=offer_id,
            status=payload.status,
            actor=context.user_id,
        )
        return _offer_payload(service, row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@public_router.get("/{token}/offers")
def supplier_offer_history(
    token: str,
    current_only: bool = False,
    limit: int = Query(default=250, ge=1, le=1000),
    engine: Engine = Depends(get_engine),
):
    service = SupplierPortalService(engine)
    access, _grant = _supplier_access(service, token, "offer:read")
    rows = service.list_offers(
        access.organization_id,
        access.facility_id,
        partner_id=access.partner_id,
        current_only=current_only,
        limit=limit,
    )
    return [_offer_payload(service, row) for row in rows]


@public_router.post("/{token}/offers", status_code=201)
def submit_supplier_offer(
    token: str,
    payload: SupplierOfferPayload,
    engine: Engine = Depends(get_engine),
):
    service = SupplierPortalService(engine)
    access, _grant = _supplier_access(service, token, "offer:submit")
    try:
        row = service.submit_offer(
            access=access,
            lines=[line.model_dump() for line in payload.lines],
            external_reference=payload.external_reference,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            promotion_terms=payload.promotion_terms,
            notes=payload.notes,
            lead_time_days=payload.lead_time_days,
        )
        return _offer_payload(service, row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@public_router.post("/{token}/offers/{offer_id}/revisions", status_code=201)
def revise_supplier_offer(
    token: str,
    offer_id: str,
    payload: SupplierOfferPayload,
    engine: Engine = Depends(get_engine),
):
    service = SupplierPortalService(engine)
    access, _grant = _supplier_access(service, token, "offer:revise")
    try:
        row = service.revise_offer(
            access=access,
            offer_id=offer_id,
            lines=[line.model_dump() for line in payload.lines],
            external_reference=payload.external_reference,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            promotion_terms=payload.promotion_terms,
            notes=payload.notes,
            lead_time_days=payload.lead_time_days,
        )
        return _offer_payload(service, row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@public_router.post("/{token}/offers/{offer_id}/withdraw")
def withdraw_supplier_offer(
    token: str,
    offer_id: str,
    engine: Engine = Depends(get_engine),
):
    service = SupplierPortalService(engine)
    access, _grant = _supplier_access(service, token, "offer:withdraw")
    try:
        row = service.withdraw_offer(access=access, offer_id=offer_id)
        return _offer_payload(service, row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
