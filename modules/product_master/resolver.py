"""Read-side Product Master resolution for search and Product 360.

This module deliberately returns plain dictionaries so read-only consumers do not
need to keep SQLAlchemy objects attached to a session.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Product

from .models import ProductAlias, ProductExternalMapping, ProductMasterProfile
from .repository import ProductMasterRepository, normalize_alias


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _event_dict(event: Any) -> dict[str, Any]:
    effective = getattr(event, "effective_at", None)
    return {
        "value_type": _clean(getattr(event, "value_type", "")),
        "amount": float(getattr(event, "amount", 0) or 0),
        "previous_amount": (
            float(getattr(event, "previous_amount"))
            if getattr(event, "previous_amount", None) is not None
            else None
        ),
        "currency": _clean(getattr(event, "currency", "USD")) or "USD",
        "source": _clean(getattr(event, "source", "")),
        "source_reference": _clean(getattr(event, "source_reference", "")),
        "partner_id": _clean(getattr(event, "partner_id", "")),
        "effective_at": effective.isoformat() if effective is not None else "",
    }


def flatten_product_master_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    product = snapshot.get("product")
    if product is None:
        return {}
    profile = snapshot.get("profile")
    vendor_rows = list(snapshot.get("vendors") or [])
    primary = next(
        (
            row
            for row in vendor_rows
            if getattr(row.get("link"), "is_primary", False)
            and getattr(row.get("link"), "active", False)
        ),
        vendor_rows[0] if vendor_rows else None,
    )
    link = primary.get("link") if primary else None
    partner = primary.get("partner") if primary else None
    mappings = [
        {
            "system_name": _clean(getattr(row, "system_name", "")),
            "external_id": _clean(getattr(row, "external_id", "")),
            "external_name": _clean(getattr(row, "external_name", "")),
        }
        for row in snapshot.get("mappings") or []
    ]
    aliases = [_clean(getattr(row, "alias", "")) for row in snapshot.get("aliases") or []]
    history = [_event_dict(row) for row in snapshot.get("value_history") or []]
    latest_by_type: dict[str, dict[str, Any]] = {}
    for row in history:
        latest_by_type.setdefault(row["value_type"], row)

    return {
        "canonical_product_id": _clean(getattr(product, "id", "")),
        "product_name": _clean(getattr(product, "name", "")),
        "sku": _clean(getattr(product, "sku", "")),
        "upc": _clean(getattr(product, "upc", "")),
        "external_product_id": _clean(getattr(product, "external_product_id", "")),
        "item_type": _clean(getattr(product, "item_type", "")),
        "base_unit": _clean(getattr(product, "base_unit", "")),
        "unit_cost": float(getattr(product, "unit_cost", 0) or 0),
        "retail_price": float(getattr(product, "retail_price", 0) or 0),
        "brand": _clean(getattr(profile, "brand", "")) if profile else "",
        "category": _clean(getattr(profile, "category", "")) if profile else "",
        "subcategory": _clean(getattr(profile, "subcategory", "")) if profile else "",
        "strain": _clean(getattr(profile, "strain", "")) if profile else "",
        "manufacturer": _clean(getattr(profile, "manufacturer", "")) if profile else "",
        "product_format": _clean(getattr(profile, "product_format", "")) if profile else "",
        "description": _clean(getattr(profile, "description", "")) if profile else "",
        "primary_vendor": _clean(getattr(partner, "name", "")) if partner else "",
        "primary_vendor_id": _clean(getattr(partner, "id", "")) if partner else "",
        "vendor_sku": _clean(getattr(link, "vendor_sku", "")) if link else "",
        "vendor_lead_time_days": int(getattr(link, "lead_time_days", 0) or 0) if link else 0,
        "vendor_moq": float(getattr(link, "minimum_order_quantity", 0) or 0) if link else 0.0,
        "vendor_case_pack": float(getattr(link, "case_pack", 0) or 0) if link else 0.0,
        "external_mappings": mappings,
        "aliases": [value for value in aliases if value],
        "value_history": history,
        "latest_values": latest_by_type,
    }


def _resolve_product_id(
    engine: Engine,
    organization_id: str,
    *,
    product_name: str = "",
    sku: str = "",
) -> str:
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    name = _clean(product_name)
    sku_value = _clean(sku)
    with sessions() as session:
        if sku_value:
            product_id = session.scalar(
                select(Product.id).where(
                    Product.organization_id == organization_id,
                    func.lower(Product.sku) == sku_value.casefold(),
                    Product.active.is_(True),
                )
            )
            if product_id:
                return str(product_id)
        if name:
            product_id = session.scalar(
                select(Product.id).where(
                    Product.organization_id == organization_id,
                    func.lower(Product.name) == name.casefold(),
                    Product.active.is_(True),
                )
            )
            if product_id:
                return str(product_id)
            normalized = normalize_alias(name)
            if normalized:
                product_id = session.scalar(
                    select(ProductAlias.product_id).where(
                        ProductAlias.organization_id == organization_id,
                        ProductAlias.normalized_alias == normalized,
                        ProductAlias.active.is_(True),
                    )
                )
                if product_id:
                    return str(product_id)
            product_id = session.scalar(
                select(ProductExternalMapping.product_id).where(
                    ProductExternalMapping.organization_id == organization_id,
                    ProductExternalMapping.active.is_(True),
                    or_(
                        func.lower(ProductExternalMapping.external_id) == name.casefold(),
                        func.lower(ProductExternalMapping.external_name) == name.casefold(),
                    ),
                )
            )
            if product_id:
                return str(product_id)
    return ""


def resolve_product_master(
    engine: Engine,
    organization_id: str,
    *,
    product_name: str = "",
    sku: str = "",
    history_limit: int = 50,
) -> dict[str, Any]:
    product_id = _resolve_product_id(
        engine,
        organization_id,
        product_name=product_name,
        sku=sku,
    )
    if not product_id:
        return {}
    snapshot = ProductMasterRepository(engine).snapshot(
        organization_id,
        product_id,
        history_limit=history_limit,
    )
    return flatten_product_master_snapshot(snapshot)


def search_product_master(
    engine: Engine,
    organization_id: str,
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    needle = normalize_alias(query)
    if len(needle) < 2:
        return []
    like = f"%{needle}%"
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    product_ids: list[str] = []

    def add(values: list[str]) -> None:
        for value in values:
            token = str(value)
            if token not in product_ids:
                product_ids.append(token)
            if len(product_ids) >= max(1, int(limit)):
                break

    with sessions() as session:
        add(
            list(
                session.scalars(
                    select(Product.id)
                    .where(
                        Product.organization_id == organization_id,
                        Product.active.is_(True),
                        or_(
                            func.lower(Product.name).like(like),
                            func.lower(Product.sku).like(like),
                            func.lower(Product.upc).like(like),
                        ),
                    )
                    .order_by(Product.name)
                    .limit(limit)
                )
            )
        )
        if len(product_ids) < limit:
            add(
                list(
                    session.scalars(
                        select(ProductAlias.product_id)
                        .where(
                            ProductAlias.organization_id == organization_id,
                            ProductAlias.active.is_(True),
                            ProductAlias.normalized_alias.like(like),
                        )
                        .limit(limit)
                    )
                )
            )
        if len(product_ids) < limit:
            add(
                list(
                    session.scalars(
                        select(ProductExternalMapping.product_id)
                        .where(
                            ProductExternalMapping.organization_id == organization_id,
                            ProductExternalMapping.active.is_(True),
                            or_(
                                func.lower(ProductExternalMapping.external_id).like(like),
                                func.lower(ProductExternalMapping.external_name).like(like),
                            ),
                        )
                        .limit(limit)
                    )
                )
            )
        if len(product_ids) < limit:
            add(
                list(
                    session.scalars(
                        select(ProductMasterProfile.product_id)
                        .where(
                            ProductMasterProfile.organization_id == organization_id,
                            or_(
                                func.lower(ProductMasterProfile.brand).like(like),
                                func.lower(ProductMasterProfile.category).like(like),
                                func.lower(ProductMasterProfile.subcategory).like(like),
                                func.lower(ProductMasterProfile.strain).like(like),
                                func.lower(ProductMasterProfile.manufacturer).like(like),
                            ),
                        )
                        .limit(limit)
                    )
                )
            )

    repo = ProductMasterRepository(engine)
    results: list[dict[str, Any]] = []
    for product_id in product_ids[:limit]:
        try:
            results.append(
                flatten_product_master_snapshot(
                    repo.snapshot(organization_id, product_id, history_limit=5)
                )
            )
        except Exception:
            continue
    return [row for row in results if row]
