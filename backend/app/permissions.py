from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.permissions import AppUserPermissionOverride

from .auth import RequestContext


PERMISSION_REGISTRY: dict[str, dict[str, str]] = {
    "wholesale.view": {"group": "Wholesale", "label": "View wholesale", "description": "View wholesale inventory, storefront configuration, and order activity."},
    "wholesale.edit_items": {"group": "Wholesale", "label": "Edit wholesale items", "description": "Change storefront visibility, featured status, and item ordering."},
    "wholesale.manage_pricing": {"group": "Wholesale", "label": "Manage wholesale pricing", "description": "Change base wholesale prices."},
    "wholesale.manage_volume_pricing": {"group": "Wholesale", "label": "Manage volume pricing", "description": "Change minimums, case quantities, and quantity-break pricing."},
    "wholesale.publish_storefront": {"group": "Wholesale", "label": "Publish storefront", "description": "Change storefront foundation settings and publish customer-facing changes."},
    "wholesale.approve_orders": {"group": "Wholesale", "label": "Approve wholesale orders", "description": "Approve, modify, or reject customer wholesale order requests."},
    "wholesale.manage_customer_pricing": {"group": "Wholesale", "label": "Manage customer pricing", "description": "Manage customer-specific commercial pricing and terms when available."},
    "wholesale.manage_design": {"group": "Wholesale", "label": "Manage storefront design", "description": "Edit Storefront Studio design, imagery, and presentation."},
}

_ALL_WHOLESALE = frozenset(PERMISSION_REGISTRY)
ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "dev": _ALL_WHOLESALE,
    "admin": _ALL_WHOLESALE,
    "supervisor": _ALL_WHOLESALE,
    "buyer": _ALL_WHOLESALE,
    "planner": frozenset({"wholesale.view"}),
    "operator": frozenset({"wholesale.view"}),
    "qa": frozenset({"wholesale.view"}),
    "read_only": frozenset({"wholesale.view"}),
    "trial": frozenset({"wholesale.view"}),
    "user": frozenset({"wholesale.view"}),
}


def permission_snapshot(context: RequestContext, engine: Engine) -> dict:
    role = context.role.casefold()
    if role == "dev":
        return {
            "role": role,
            "effective": {key: True for key in PERMISSION_REGISTRY},
            "source": {key: "dev" for key in PERMISSION_REGISTRY},
        }

    defaults = ROLE_DEFAULTS.get(role, frozenset({"wholesale.view"}))
    effective = {key: key in defaults for key in PERMISSION_REGISTRY}
    source = {key: "role" for key in PERMISSION_REGISTRY}
    with Session(engine) as session:
        rows = session.scalars(
            select(AppUserPermissionOverride).where(
                AppUserPermissionOverride.user_id == context.user_id,
                AppUserPermissionOverride.organization_id == context.organization_id,
                AppUserPermissionOverride.facility_id == context.facility_id,
            )
        ).all()
    for row in rows:
        if row.permission not in PERMISSION_REGISTRY:
            continue
        effective[row.permission] = row.effect == "allow"
        source[row.permission] = row.effect
    return {"role": role, "effective": effective, "source": source}


def has_permission(context: RequestContext, engine: Engine, permission: str) -> bool:
    if permission not in PERMISSION_REGISTRY:
        raise RuntimeError(f"Unknown permission: {permission}")
    return bool(permission_snapshot(context, engine)["effective"].get(permission))


def require_permission(context: RequestContext, engine: Engine, permission: str) -> None:
    if not has_permission(context, engine, permission):
        label = PERMISSION_REGISTRY[permission]["label"]
        raise HTTPException(403, f"Your account does not have permission to {label.casefold()} at this facility.")
