"""Per-listing storefront sales-unit controls with tenant-safe conversion."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Product, utc_now
from modules.commerce_storefronts.models import CommerceStorefrontProduct
from modules.commerce_storefronts.sales_units import (
    StorefrontProductSalesUnit,
    compatible_sales_units,
    convert_quantity,
    convert_unit_price,
    normalize_unit,
)
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService

from ..auth import RequestContext, get_request_context, require_facility_capability
from ..database import get_engine
from ..permissions import require_permission


router = APIRouter(prefix="/storefronts/sales-units", tags=["storefronts"])


class SalesUnitPayload(BaseModel):
    sales_unit: str = Field(min_length=1, max_length=24)


def _authorize(context: RequestContext, engine: Engine, *, write: bool = False) -> None:
    require_facility_capability(context, engine, "commercial")
    require_permission(context, engine, "wholesale.view")
    if write:
        require_permission(context, engine, "wholesale.edit_items")
        require_permission(context, engine, "wholesale.manage_pricing")
        require_permission(context, engine, "wholesale.manage_volume_pricing")


@router.get("")
def storefront_sales_units(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _authorize(context, engine)
    service = WholesaleCommerceStorefrontService(engine)
    snapshot = service.admin_snapshot(context.organization_id, context.facility_id)
    return {
        "storefront": snapshot.get("storefront"),
        "products": [
            {
                "product_id": row.get("product_id"),
                "sku": row.get("sku", ""),
                "name": row.get("name", ""),
                "base_unit": row.get("base_unit") or row.get("unit", ""),
                "sales_unit": row.get("sales_unit") or row.get("unit", ""),
                "compatible_sales_units": row.get("compatible_sales_units") or [row.get("unit", "")],
                "price_usd": float(row.get("price_usd") or 0.0),
                "minimum_quantity": float(row.get("minimum_quantity") or 1.0),
                "case_quantity": float(row.get("case_quantity") or 1.0),
                "active": bool(row.get("active", False)),
            }
            for row in snapshot.get("products", [])
            if row.get("product_id")
        ],
    }


@router.post("/{product_id}")
def update_storefront_sales_unit(
    product_id: str,
    payload: SalesUnitPayload,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _authorize(context, engine, write=True)
    service = WholesaleCommerceStorefrontService(engine)
    storefront = service.get_storefront(context.organization_id, context.facility_id)
    if not storefront:
        raise HTTPException(404, "Create the storefront before changing listing sales units.")

    with Session(engine) as session, session.begin():
        product = session.get(Product, product_id)
        if not product or product.organization_id != context.organization_id or not product.active:
            raise HTTPException(404, "Product was not found in this organization.")
        listing = session.scalar(
            select(CommerceStorefrontProduct).where(
                CommerceStorefrontProduct.storefront_id == storefront.id,
                CommerceStorefrontProduct.organization_id == context.organization_id,
                CommerceStorefrontProduct.product_id == product.id,
            )
        )
        if not listing:
            raise HTTPException(404, "Product is not currently configured on this storefront.")

        base_unit = normalize_unit(product.base_unit)
        target_unit = normalize_unit(payload.sales_unit)
        allowed = compatible_sales_units(base_unit)
        if target_unit not in allowed:
            raise HTTPException(422, f"{target_unit or payload.sales_unit} is not compatible with inventory unit {base_unit or product.base_unit}.")

        setting = session.scalar(
            select(StorefrontProductSalesUnit).where(
                StorefrontProductSalesUnit.storefront_id == storefront.id,
                StorefrontProductSalesUnit.product_id == product.id,
            )
        )
        old_unit = normalize_unit(setting.sales_unit) if setting else base_unit
        if target_unit != old_unit:
            try:
                listing.minimum_quantity = convert_quantity(listing.minimum_quantity, old_unit, target_unit)
                listing.case_quantity = convert_quantity(listing.case_quantity, old_unit, target_unit)
                listing.price_usd = convert_unit_price(listing.price_usd, old_unit, target_unit)
                tiers = json.loads(listing.quantity_breaks_json or "[]")
                for tier in tiers:
                    tier["minimum_quantity"] = convert_quantity(float(tier.get("minimum_quantity") or 0.0), old_unit, target_unit)
                    tier["price_usd"] = convert_unit_price(float(tier.get("price_usd") or 0.0), old_unit, target_unit)
                listing.quantity_breaks_json = json.dumps(tiers, sort_keys=True, separators=(",", ":"))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

        if setting is None:
            setting = StorefrontProductSalesUnit(
                organization_id=context.organization_id,
                storefront_id=storefront.id,
                product_id=product.id,
                sales_unit=target_unit,
                updated_by=context.user_id,
            )
            session.add(setting)
        else:
            setting.sales_unit = target_unit
            setting.updated_by = context.user_id
            setting.updated_at = utc_now()

        session.add(
            AuditEvent(
                organization_id=context.organization_id,
                facility_id=context.facility_id,
                entity_type="commerce_storefront_product",
                entity_id=listing.id,
                action="storefront_sales_unit_changed",
                actor=context.user_id,
                changes_json=json.dumps(
                    {
                        "product_id": product.id,
                        "from_unit": old_unit,
                        "to_unit": target_unit,
                        "minimum_quantity": listing.minimum_quantity,
                        "case_quantity": listing.case_quantity,
                        "price_usd": listing.price_usd,
                    },
                    sort_keys=True,
                ),
            )
        )
        session.flush()

    refreshed = service.admin_snapshot(context.organization_id, context.facility_id)
    row = next((item for item in refreshed.get("products", []) if item.get("product_id") == product_id), None)
    if not row:
        raise HTTPException(500, "Sales unit saved but refreshed listing could not be resolved.")
    return row
