from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, Facility, Organization
from modules.commerce_storefronts.models import (
    CommerceStorefront,
    CommerceStorefrontOrderRequest,
    CommerceStorefrontProduct,
)
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/admin/storefronts", tags=["admin"])


class StorefrontOwnershipUpdate(BaseModel):
    organization_id: str
    facility_id: str
    clear_catalog: bool = False


def _require_dev(context: RequestContext) -> None:
    if context.role.casefold() != "dev":
        raise HTTPException(403, "Level DEV access is required to edit storefront ownership.")


def _counts(session: Session, storefront_id: str) -> tuple[int, int]:
    listing_count = int(
        session.scalar(
            select(func.count()).select_from(CommerceStorefrontProduct).where(
                CommerceStorefrontProduct.storefront_id == storefront_id
            )
        )
        or 0
    )
    request_count = int(
        session.scalar(
            select(func.count()).select_from(CommerceStorefrontOrderRequest).where(
                CommerceStorefrontOrderRequest.storefront_id == storefront_id
            )
        )
        or 0
    )
    return listing_count, request_count


def _serialize(session: Session, row: CommerceStorefront) -> dict:
    organization = session.get(Organization, row.organization_id)
    facility = session.get(Facility, row.facility_id)
    listing_count, request_count = _counts(session, row.id)
    return {
        "id": row.id,
        "display_name": row.display_name,
        "slug": row.slug,
        "subdomain": row.subdomain,
        "hostname": f"{row.subdomain}.doobielogic.io",
        "published": row.published,
        "organization_id": row.organization_id,
        "organization_name": organization.name if organization else "Unknown organization",
        "organization_slug": organization.slug if organization else "",
        "facility_id": row.facility_id,
        "facility_name": facility.name if facility else "Unknown facility",
        "facility_code": facility.code if facility else "",
        "listing_count": listing_count,
        "request_count": request_count,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
def list_storefront_ownership(
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """List every hosted storefront and its durable tenant ownership for DEV admins."""

    _require_dev(context)
    with Session(engine) as session:
        rows = session.scalars(
            select(CommerceStorefront).order_by(CommerceStorefront.display_name, CommerceStorefront.subdomain)
        ).all()
        return [_serialize(session, row) for row in rows]


@router.post("/{storefront_id}/ownership")
def update_storefront_ownership(
    storefront_id: str,
    payload: StorefrontOwnershipUpdate,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    """Move a storefront to the intended organization/facility without leaking tenant data.

    Cross-organization moves are blocked when order requests already exist because
    those requests are immutable tenant history. Existing catalog listings must
    either be absent or explicitly cleared because product IDs belong to the old
    organization and must never follow the storefront into a different tenant.
    """

    _require_dev(context)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        row = session.get(CommerceStorefront, storefront_id)
        if row is None:
            raise HTTPException(404, "Storefront was not found.")

        organization = session.get(Organization, payload.organization_id)
        if organization is None or not organization.active:
            raise HTTPException(400, "Target organization must exist and be active.")

        facility = session.get(Facility, payload.facility_id)
        if facility is None or not facility.active:
            raise HTTPException(400, "Target facility must exist and be active.")
        if facility.organization_id != organization.id:
            raise HTTPException(400, "Target facility does not belong to the selected organization.")
        if not facility.commercial_enabled:
            raise HTTPException(400, "Target facility must enable Commercial operations for a storefront.")

        old_organization_id = row.organization_id
        old_facility_id = row.facility_id
        organization_changed = old_organization_id != organization.id
        listing_count, request_count = _counts(session, row.id)

        if organization_changed and request_count:
            raise HTTPException(
                409,
                "This storefront has order-request history and cannot be moved across organizations. "
                "Create a new storefront instead so historical tenant ownership remains intact.",
            )
        if organization_changed and listing_count and not payload.clear_catalog:
            raise HTTPException(
                409,
                "This storefront has catalog listings from the current organization. "
                "Confirm catalog clearing before moving it to another organization.",
            )

        cleared_catalog = 0
        if organization_changed and listing_count:
            result = session.execute(
                delete(CommerceStorefrontProduct).where(CommerceStorefrontProduct.storefront_id == row.id)
            )
            cleared_catalog = int(result.rowcount or 0)

        row.organization_id = organization.id
        row.facility_id = facility.id
        row.updated_by = context.user_id
        session.flush()

        changes = {
            "organization_id": {"before": old_organization_id, "after": row.organization_id},
            "facility_id": {"before": old_facility_id, "after": row.facility_id},
            "catalog_listings_cleared": cleared_catalog,
            "hostname": f"{row.subdomain}.doobielogic.io",
        }
        session.add(
            AuditEvent(
                organization_id=row.organization_id,
                facility_id=row.facility_id,
                entity_type="commerce_storefront",
                entity_id=row.id,
                action="storefront_ownership_updated",
                actor=context.user_id,
                changes_json=json.dumps(changes, sort_keys=True),
            )
        )
        session.flush()
        result = _serialize(session, row)

    return result
