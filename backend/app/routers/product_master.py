from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Product
from modules.product_master import ProductMasterRepository
from modules.product_master.models import ProductMasterProfile
from ..auth import RequestContext, get_request_context, require_facility_capability, require_inventory_operation_capability
from ..database import get_engine

router = APIRouter(prefix="/product-master", tags=["product-master"])
WRITE_ROLES = {"dev", "admin", "supervisor", "operator"}
ITEM_TYPES = {"cannabis", "packaging", "wip", "finished_good"}


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    item_type: str
    base_unit: str = Field(default="unit", min_length=1, max_length=32)
    upc: str = Field(default="", max_length=64)
    external_product_id: str = Field(default="", max_length=120)
    retail_enabled: bool = True
    production_enabled: bool = True


class ProductIdentityUpdate(ProductCreate):
    active: bool = True


class ProfileUpdate(BaseModel):
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    strain: str = ""
    manufacturer: str = ""
    product_format: str = ""
    description: str = ""
    retail_enabled: bool = True
    production_enabled: bool = True


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=512)
    source: str = Field(default="manual", max_length=120)


class MappingCreate(BaseModel):
    system_name: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    external_name: str = Field(default="", max_length=512)


class ValueCreate(BaseModel):
    value_type: str
    amount: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    source: str = Field(default="manual", max_length=120)
    source_reference: str = Field(default="", max_length=255)


def _require_write(context: RequestContext) -> None:
    if context.role.casefold() not in WRITE_ROLES:
        raise HTTPException(403, "Your role does not allow catalog changes.")


def _require_operation(context: RequestContext, engine: Engine, operation: str) -> str:
    operation = operation.strip().casefold()
    if operation not in {"retail", "production"}:
        raise HTTPException(422, "Operation must be retail or production.")
    require_inventory_operation_capability(context, engine, operation)
    return operation


def _require_enabled_scopes(context: RequestContext, engine: Engine, *, retail: bool, production: bool) -> None:
    if not retail and not production:
        raise HTTPException(422, "A catalog product must be enabled for Retail Ops or Production Ops.")
    if retail:
        require_facility_capability(context, engine, "retail")
    if production:
        require_inventory_operation_capability(context, engine, "production")


def _identity(row: Product) -> dict:
    return {key: getattr(row, key) for key in ("id", "sku", "name", "item_type", "base_unit", "unit_cost", "retail_price", "upc", "external_product_id", "active", "created_at", "updated_at")}


def _snapshot(engine: Engine, organization_id: str, product_id: str) -> dict:
    snap = ProductMasterRepository(engine).snapshot(organization_id, product_id)
    profile = snap["profile"]
    return {
        "product": _identity(snap["product"]),
        "profile": {key: getattr(profile, key) for key in ("brand", "category", "subcategory", "strain", "manufacturer", "product_format", "description", "retail_enabled", "production_enabled")} if profile else None,
        "vendors": [{"id": item["link"].id, "partner_id": item["link"].partner_id, "partner_name": item["partner"].name if item["partner"] else "Unknown vendor", "vendor_sku": item["link"].vendor_sku, "is_primary": item["link"].is_primary, "lead_time_days": item["link"].lead_time_days, "minimum_order_quantity": item["link"].minimum_order_quantity, "case_pack": item["link"].case_pack} for item in snap["vendors"]],
        "mappings": [{key: getattr(row, key) for key in ("id", "system_name", "external_id", "external_name", "active")} for row in snap["mappings"]],
        "aliases": [{key: getattr(row, key) for key in ("id", "alias", "source", "active")} for row in snap["aliases"]],
        "value_history": [{key: getattr(row, key) for key in ("id", "value_type", "amount", "previous_amount", "currency", "source", "source_reference", "actor", "effective_at")} for row in snap["value_history"]],
    }


def _validate_identity(session, organization_id: str, payload: ProductCreate, exclude_id: str | None = None) -> dict:
    values = payload.model_dump(exclude={"retail_enabled", "production_enabled"})
    values.update({key: str(values[key] or "").strip() for key in ("sku", "name", "base_unit", "upc", "external_product_id")})
    values["item_type"] = str(values["item_type"] or "").strip().casefold()
    if values["item_type"] not in ITEM_TYPES:
        raise HTTPException(422, f"Item type must be one of: {', '.join(sorted(ITEM_TYPES))}.")
    duplicate = session.scalar(select(Product).where(Product.organization_id == organization_id, Product.sku == values["sku"], Product.id != (exclude_id or "")))
    if duplicate:
        raise HTTPException(409, "SKU already belongs to another catalog product.")
    if values["upc"]:
        duplicate = session.scalar(select(Product).where(Product.organization_id == organization_id, Product.upc == values["upc"], Product.id != (exclude_id or "")))
        if duplicate:
            raise HTTPException(409, "UPC already belongs to another catalog product.")
    return values


@router.get("")
def list_products(search: str = Query(default="", max_length=200), status: str = "active", item_type: str = "", operation: str = "retail", context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    operation = _require_operation(context, engine, operation)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        query = select(Product, ProductMasterProfile).outerjoin(ProductMasterProfile, ProductMasterProfile.product_id == Product.id).where(Product.organization_id == context.organization_id)
        if status == "active": query = query.where(Product.active.is_(True))
        elif status == "archived": query = query.where(Product.active.is_(False))
        if item_type: query = query.where(Product.item_type == item_type)
        if search.strip():
            term = f"%{search.strip()}%"
            query = query.where(or_(Product.name.ilike(term), Product.sku.ilike(term), Product.upc.ilike(term), Product.external_product_id.ilike(term)))
        rows = list(session.execute(query.order_by(Product.active.desc(), Product.name).limit(500)))
        result = []
        for row, profile in rows:
            retail_enabled = profile.retail_enabled if profile else True
            production_enabled = profile.production_enabled if profile else True
            if operation == "retail" and not retail_enabled: continue
            if operation == "production" and not production_enabled: continue
            result.append({**_identity(row), "retail_enabled": retail_enabled, "production_enabled": production_enabled, "brand": profile.brand if profile else "", "category": profile.category if profile else "", "product_format": profile.product_format if profile else ""})
        return result


@router.post("", status_code=201)
def create_product(payload: ProductCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_write(context)
    _require_enabled_scopes(context, engine, retail=payload.retail_enabled, production=payload.production_enabled)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        values = _validate_identity(session, context.organization_id, payload)
        row = Product(organization_id=context.organization_id, **values)
        session.add(row); session.flush()
        session.add(ProductMasterProfile(organization_id=context.organization_id, product_id=row.id, retail_enabled=payload.retail_enabled, production_enabled=payload.production_enabled))
        session.add(AuditEvent(organization_id=context.organization_id, entity_type="product", entity_id=row.id, action="catalog_product_created", actor=context.user_id, changes_json=json.dumps(values, sort_keys=True)))
    return _identity(row)


@router.get("/{product_id}")
def product_detail(product_id: str, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    try: return _snapshot(engine, context.organization_id, product_id)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc


@router.post("/{product_id}/identity")
def update_identity(product_id: str, payload: ProductIdentityUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_write(context)
    _require_enabled_scopes(context, engine, retail=payload.retail_enabled, production=payload.production_enabled)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        row = session.get(Product, product_id)
        if not row or row.organization_id != context.organization_id: raise HTTPException(404, "Catalog product was not found.")
        values = _validate_identity(session, context.organization_id, payload, product_id)
        values["active"] = payload.active
        before = {key: getattr(row, key) for key in values}
        for key, value in values.items(): setattr(row, key, value)
        profile = session.get(ProductMasterProfile, product_id)
        if profile is None:
            profile = ProductMasterProfile(organization_id=context.organization_id, product_id=product_id)
            session.add(profile)
        profile.retail_enabled = payload.retail_enabled
        profile.production_enabled = payload.production_enabled
        session.add(AuditEvent(organization_id=context.organization_id, entity_type="product", entity_id=row.id, action="catalog_product_updated", actor=context.user_id, changes_json=json.dumps({"before": before, "after": values}, sort_keys=True)))
    return _identity(row)


@router.post("/{product_id}/profile")
def update_profile(product_id: str, payload: ProfileUpdate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_write(context)
    _require_enabled_scopes(context, engine, retail=payload.retail_enabled, production=payload.production_enabled)
    try:
        ProductMasterRepository(engine).update_profile(context.organization_id, product_id, actor=context.user_id, **payload.model_dump())
        return _snapshot(engine, context.organization_id, product_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/{product_id}/aliases", status_code=201)
def add_alias(product_id: str, payload: AliasCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_write(context)
    try:
        row = ProductMasterRepository(engine).add_alias(context.organization_id, product_id, payload.alias, actor=context.user_id, source=payload.source)
        return {"id": row.id, "alias": row.alias, "source": row.source}
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc


@router.post("/{product_id}/mappings", status_code=201)
def add_mapping(product_id: str, payload: MappingCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_write(context)
    try:
        row = ProductMasterRepository(engine).map_external(context.organization_id, product_id, actor=context.user_id, **payload.model_dump())
        return {"id": row.id, "system_name": row.system_name, "external_id": row.external_id, "external_name": row.external_name}
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc


@router.post("/{product_id}/values", status_code=201)
def record_value(product_id: str, payload: ValueCreate, context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _require_write(context)
    try:
        row = ProductMasterRepository(engine).record_value(context.organization_id, product_id, actor=context.user_id, **payload.model_dump())
        return {key: getattr(row, key) for key in ("id", "value_type", "amount", "previous_amount", "currency", "effective_at")}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
