"""DoobieCommerce hosted storefront builder, public catalog, approval queue, and wholesale intelligence."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from modules.commerce_storefronts.intelligence import StorefrontWholesaleIntelligenceService
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService as CommerceStorefrontService

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine

router = APIRouter(prefix="/storefronts", tags=["storefronts"])
public_router = APIRouter(prefix="/commerce-storefronts", tags=["commerce-storefronts"])
_STORE_ROLES = {"dev", "admin", "supervisor", "buyer"}


def _authorize_read(context: RequestContext, engine: Engine) -> None:
    require_facility_capability(context, engine, "commercial")


def _authorize_manage(context: RequestContext, engine: Engine) -> None:
    _authorize_read(context, engine)
    if context.role.casefold() not in _STORE_ROLES:
        raise HTTPException(403, "Your role is not authorized to manage the hosted storefront or approve public orders.")


class StorefrontPayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    subdomain: str = Field(min_length=2, max_length=63)
    headline: str = Field(default="Wholesale ordering", max_length=255)
    description: str = Field(default="", max_length=5000)
    logo_url: str = Field(default="", max_length=2048)
    hero_image_url: str = Field(default="", max_length=2048)
    accent_color: str = Field(default="#8abf55", min_length=7, max_length=7)
    contact_email: str = Field(default="", max_length=320)
    order_instructions: str = Field(default="", max_length=5000)
    published: bool = False


class QuantityBreakPayload(BaseModel):
    minimum_quantity: float = Field(gt=0)
    price_usd: float = Field(ge=0)


class StorefrontProductPayload(BaseModel):
    product_id: str
    price_usd: float = Field(ge=0)
    minimum_quantity: float = Field(default=1, gt=0)
    case_quantity: float = Field(default=1, gt=0)
    quantity_breaks: list[QuantityBreakPayload] = Field(default_factory=list, max_length=20)
    featured: bool = False
    active: bool = True
    sort_order: int = 0


class StorefrontProductsPayload(BaseModel):
    products: list[StorefrontProductPayload] = Field(default_factory=list, max_length=1000)


class PublicOrderLine(BaseModel):
    product_id: str
    quantity: float = Field(gt=0)


class PublicOrderPayload(BaseModel):
    buyer_company: str = Field(min_length=1, max_length=255)
    buyer_license: str = Field(default="", max_length=255)
    buyer_contact: str = Field(min_length=1, max_length=255)
    buyer_email: str = Field(min_length=3, max_length=320)
    buyer_phone: str = Field(default="", max_length=64)
    lines: list[PublicOrderLine] = Field(min_length=1, max_length=250)
    requested_delivery_date: date | None = None
    requested_delivery_window: str = Field(default="", max_length=80)
    purchase_order_reference: str = Field(default="", max_length=255)
    purchase_order_attachment_name: str = Field(default="", max_length=255)
    purchase_order_attachment_type: str = Field(default="", max_length=128)
    purchase_order_attachment_base64: str = Field(default="", max_length=4_500_000)
    notes: str = Field(default="", max_length=5000)


class ReviewLinePayload(BaseModel):
    product_id: str
    quantity: float = Field(gt=0)
    price_usd: float = Field(ge=0)


class ReviewPayload(BaseModel):
    note: str = Field(default="", max_length=2000)
    lines: list[ReviewLinePayload] | None = Field(default=None, max_length=250)


class PublicStatusPayload(BaseModel):
    request_id: str = Field(min_length=6, max_length=64)
    buyer_email: str = Field(min_length=3, max_length=320)


class AgentQuestionPayload(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.get("")
def storefront_snapshot(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    return CommerceStorefrontService(engine).admin_snapshot(context.organization_id, context.facility_id)


@router.post("")
def save_storefront(payload: StorefrontPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_manage(context, engine)
    try:
        row = CommerceStorefrontService(engine).upsert_storefront(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return CommerceStorefrontService._storefront_dict(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/wholesale-inventory")
def wholesale_inventory(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    return CommerceStorefrontService(engine).wholesale_inventory(context.organization_id, context.facility_id)


@router.get("/catalog-options")
def catalog_options(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    return CommerceStorefrontService(engine).merchandising_catalog_options(context.organization_id, context.facility_id)


@router.post("/products")
def save_storefront_products(payload: StorefrontProductsPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_manage(context, engine)
    try:
        service = CommerceStorefrontService(engine)
        service.set_products(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, products=[row.model_dump() for row in payload.products])
        return service.admin_snapshot(context.organization_id, context.facility_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/orders/{request_id}/approve")
def approve_storefront_order(request_id: str, payload: ReviewPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_manage(context, engine)
    try:
        return CommerceStorefrontService(engine).approve_order_request(organization_id=context.organization_id, facility_id=context.facility_id, request_id=request_id, actor=context.user_id, review_note=payload.note, approved_lines=[row.model_dump() for row in payload.lines] if payload.lines is not None else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/orders/{request_id}/reject")
def reject_storefront_order(request_id: str, payload: ReviewPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_manage(context, engine)
    try:
        return CommerceStorefrontService(engine).reject_order_request(organization_id=context.organization_id, facility_id=context.facility_id, request_id=request_id, actor=context.user_id, review_note=payload.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/orders/{request_id}/purchase-order")
def download_purchase_order(request_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    try:
        attachment = CommerceStorefrontService(engine).purchase_order_attachment(organization_id=context.organization_id, facility_id=context.facility_id, request_id=request_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(content=attachment["content"], media_type=attachment["content_type"], headers={"Content-Disposition": f'attachment; filename="{attachment["file_name"].replace(chr(34), "_")}"', "X-Content-SHA256": attachment["sha256"]})


@router.get("/agent/snapshot")
def storefront_agent_snapshot(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    return StorefrontWholesaleIntelligenceService(engine).snapshot(context.organization_id, context.facility_id)


@router.post("/agent/ask")
def storefront_agent_ask(payload: AgentQuestionPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    return StorefrontWholesaleIntelligenceService(engine).answer(context.organization_id, context.facility_id, payload.question)


@public_router.post("/{slug}/orders/status")
def storefront_order_status(slug: str, payload: PublicStatusPayload, engine: Engine = Depends(get_engine)):
    try:
        return CommerceStorefrontService(engine).public_order_status(slug=slug, request_id=payload.request_id, buyer_email=payload.buyer_email)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@public_router.get("/{slug}")
def public_storefront(slug: str, engine: Engine = Depends(get_engine)):
    try:
        return CommerceStorefrontService(engine).public_catalog(slug)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@public_router.post("/{slug}/orders")
def submit_storefront_order(slug: str, payload: PublicOrderPayload, engine: Engine = Depends(get_engine)):
    try:
        row = CommerceStorefrontService(engine).submit_order_request(slug=slug, **payload.model_dump())
        return {"request_id": row.id, "status": row.status, "estimated_subtotal": row.estimated_subtotal, "message": "Order request submitted for supplier approval."}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
