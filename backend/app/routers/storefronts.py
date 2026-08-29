"""DoobieCommerce hosted storefront builder, public catalog, approval queue, and wholesale intelligence."""

from __future__ import annotations

import base64
import binascii
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Engine

from modules.commerce_storefronts.intelligence import StorefrontWholesaleIntelligenceService
from modules.commerce_storefronts.studio import CommerceStorefrontStudioService
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService as CommerceStorefrontService

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..permissions import has_permission, permission_snapshot, require_permission

router = APIRouter(prefix="/storefronts", tags=["storefronts"])
public_router = APIRouter(prefix="/commerce-storefronts", tags=["commerce-storefronts"])
_ALLOWED_PO_TYPES = {"application/pdf", "image/png", "image/jpeg"}
_MAX_PO_BYTES = 3 * 1024 * 1024


def _authorize(context: RequestContext, engine: Engine, permission: str) -> None:
    require_facility_capability(context, engine, "commercial")
    require_permission(context, engine, permission)


def _authorize_read(context: RequestContext, engine: Engine) -> None:
    _authorize(context, engine, "wholesale.view")


def _po_signature_matches(content_type: str, content: bytes) -> bool:
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    return False


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


class StudioDesignPayload(BaseModel):
    theme_preset: str = Field(default="clean", max_length=24)
    font_preset: str = Field(default="modern", max_length=24)
    card_style: str = Field(default="collectible", max_length=24)
    card_image_style: str = Field(default="cover", max_length=24)
    accent_color: str = Field(default="#8abf55", min_length=7, max_length=7)
    secondary_color: str = Field(default="#173127", min_length=7, max_length=7)
    surface_color: str = Field(default="#f7f5ef", min_length=7, max_length=7)
    announcement_enabled: bool = False
    announcement_text: str = Field(default="", max_length=240)
    show_hero: bool = True
    show_featured: bool = True
    show_about: bool = False
    about_heading: str = Field(default="Brand story", max_length=120)
    about_body: str = Field(default="", max_length=4000)
    show_contact: bool = True
    show_footer: bool = True
    section_order: list[str] = Field(default_factory=lambda: ["hero", "featured", "catalog", "about", "contact"], max_length=5)
    visible_stats: list[str] = Field(default_factory=lambda: ["thca", "tac", "terpenes", "batch", "coa", "harvest_date", "available"], max_length=16)
    badges: list[str] = Field(default_factory=lambda: ["featured", "new_drop", "limited"], max_length=8)
    logo_asset_id: str = Field(default="", max_length=36)
    hero_asset_id: str = Field(default="", max_length=36)
    favicon_asset_id: str = Field(default="", max_length=36)


class StudioAssetPayload(BaseModel):
    kind: str = Field(max_length=24)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=64)
    content_base64: str = Field(min_length=4, max_length=6_000_000)


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

    @model_validator(mode="after")
    def validate_quantity_break_thresholds(self):
        seen: set[float] = set()
        for tier in self.quantity_breaks:
            threshold = round(float(tier.minimum_quantity), 7)
            if threshold in seen:
                raise ValueError("Quantity-break minimums must be unique.")
            seen.add(threshold)
        return self


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

    @model_validator(mode="after")
    def validate_purchase_order_attachment(self):
        encoded = self.purchase_order_attachment_base64.strip()
        if not encoded:
            if self.purchase_order_attachment_name or self.purchase_order_attachment_type:
                raise ValueError("Purchase-order attachment metadata requires file content.")
            return self
        content_type = self.purchase_order_attachment_type.strip().casefold()
        if content_type not in _ALLOWED_PO_TYPES:
            raise ValueError("Purchase-order attachment must be a PDF, PNG, or JPEG.")
        raw = encoded
        if raw.casefold().startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            content = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Purchase-order attachment is not valid base64 data.") from exc
        if not content:
            raise ValueError("Purchase-order attachment is empty.")
        if len(content) > _MAX_PO_BYTES:
            raise ValueError("Purchase-order attachment must be 3 MB or smaller.")
        if not _po_signature_matches(content_type, content):
            raise ValueError("Purchase-order attachment contents do not match the declared file type.")
        return self


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


def _tier_signature(row: dict) -> tuple:
    return tuple((round(float(tier.get("minimum_quantity") or 0), 7), round(float(tier.get("price_usd") or 0), 2)) for tier in row.get("quantity_breaks") or [])


def _validate_product_permissions(payload: StorefrontProductsPayload, context: RequestContext, engine: Engine, service: CommerceStorefrontService) -> None:
    can_price = has_permission(context, engine, "wholesale.manage_pricing")
    can_volume = has_permission(context, engine, "wholesale.manage_volume_pricing")
    existing = {row["product_id"]: row for row in service.admin_snapshot(context.organization_id, context.facility_id).get("products", [])}
    for incoming_model in payload.products:
        incoming = incoming_model.model_dump()
        current = existing.get(incoming["product_id"])
        if current is None:
            if not can_price:
                raise HTTPException(403, "Adding a wholesale item requires wholesale pricing permission.")
            if not can_volume:
                raise HTTPException(403, "Adding a wholesale item requires volume-pricing permission.")
            continue
        if not can_price and round(float(incoming["price_usd"]), 2) != round(float(current.get("price_usd") or 0), 2):
            raise HTTPException(403, "Your account cannot change wholesale base pricing.")
        if not can_volume:
            volume_changed = (
                round(float(incoming["minimum_quantity"]), 7) != round(float(current.get("minimum_quantity") or 0), 7)
                or round(float(incoming["case_quantity"]), 7) != round(float(current.get("case_quantity") or 0), 7)
                or _tier_signature(incoming) != _tier_signature(current)
            )
            if volume_changed:
                raise HTTPException(403, "Your account cannot change wholesale minimums, cases, or volume pricing.")


@router.get("")
def storefront_snapshot(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    service = CommerceStorefrontService(engine)
    snapshot = service.admin_snapshot(context.organization_id, context.facility_id)
    snapshot["studio"] = CommerceStorefrontStudioService(engine).snapshot(context.organization_id, context.facility_id) if snapshot.get("storefront") else None
    snapshot["permissions"] = permission_snapshot(context, engine)
    return snapshot


@router.post("")
def save_storefront(payload: StorefrontPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize(context, engine, "wholesale.publish_storefront")
    try:
        row = CommerceStorefrontService(engine).upsert_storefront(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
        return CommerceStorefrontService._storefront_dict(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/studio")
def storefront_studio(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    try:
        return CommerceStorefrontStudioService(engine).snapshot(context.organization_id, context.facility_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/studio")
def save_storefront_studio(payload: StudioDesignPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize(context, engine, "wholesale.manage_design")
    try:
        return CommerceStorefrontStudioService(engine).save_draft(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, design=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/studio/publish")
def publish_storefront_studio(context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize(context, engine, "wholesale.manage_design")
    require_permission(context, engine, "wholesale.publish_storefront")
    try:
        return CommerceStorefrontStudioService(engine).publish_draft(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/studio/assets")
def upload_storefront_studio_asset(payload: StudioAssetPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize(context, engine, "wholesale.manage_design")
    try:
        return CommerceStorefrontStudioService(engine).upload_asset(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/studio/assets/{asset_id}")
def admin_storefront_studio_asset(asset_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize_read(context, engine)
    try:
        asset = CommerceStorefrontStudioService(engine).get_admin_asset(organization_id=context.organization_id, facility_id=context.facility_id, asset_id=asset_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(content=asset["content"], media_type=asset["content_type"], headers={"Cache-Control": "private, no-store, max-age=0", "X-Content-Type-Options": "nosniff"})


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
    _authorize(context, engine, "wholesale.edit_items")
    try:
        service = CommerceStorefrontService(engine)
        _validate_product_permissions(payload, context, engine, service)
        service.set_products(organization_id=context.organization_id, facility_id=context.facility_id, actor=context.user_id, products=[row.model_dump() for row in payload.products])
        result = service.admin_snapshot(context.organization_id, context.facility_id)
        result["permissions"] = permission_snapshot(context, engine)
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/orders/{request_id}/approve")
def approve_storefront_order(request_id: str, payload: ReviewPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize(context, engine, "wholesale.approve_orders")
    try:
        return CommerceStorefrontService(engine).approve_order_request(organization_id=context.organization_id, facility_id=context.facility_id, request_id=request_id, actor=context.user_id, review_note=payload.note, approved_lines=[row.model_dump() for row in payload.lines] if payload.lines is not None else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/orders/{request_id}/reject")
def reject_storefront_order(request_id: str, payload: ReviewPayload, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _authorize(context, engine, "wholesale.approve_orders")
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
    safe_name = attachment["file_name"].replace('"', "_").replace("\r", "_").replace("\n", "_")
    return Response(content=attachment["content"], media_type=attachment["content_type"], headers={"Content-Disposition": f'attachment; filename="{safe_name}"', "X-Content-SHA256": attachment["sha256"], "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store, max-age=0"})


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


@public_router.get("/{slug}/assets/{asset_id}")
def public_storefront_asset(slug: str, asset_id: str, engine: Engine = Depends(get_engine)):
    try:
        asset = CommerceStorefrontStudioService(engine).get_public_asset(slug=slug, asset_id=asset_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(content=asset["content"], media_type=asset["content_type"], headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{asset["sha256"]}"', "X-Content-Type-Options": "nosniff"})


@public_router.get("/{slug}")
def public_storefront(slug: str, engine: Engine = Depends(get_engine)):
    try:
        result = CommerceStorefrontService(engine).public_catalog(slug)
        result["storefront"]["studio"] = CommerceStorefrontStudioService(engine).public_design(slug)
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@public_router.post("/{slug}/orders")
def submit_storefront_order(slug: str, payload: PublicOrderPayload, engine: Engine = Depends(get_engine)):
    try:
        row = CommerceStorefrontService(engine).submit_order_request(slug=slug, **payload.model_dump())
        return {"request_id": row.id, "status": row.status, "estimated_subtotal": row.estimated_subtotal, "message": "Order request submitted for supplier approval."}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
