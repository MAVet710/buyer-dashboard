"""Transaction-safe cutover matching installed on the migration service.

The migration staging transaction must never open a second ORM session while its
batch and records are still uncommitted. Exact identifiers can auto-match; weaker
name candidates are advisory only and stay inside the caller's existing session.
"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import and_, func, select

from modules.coman.models import Product, TradePartner
from modules.product_master.models import ProductAlias, ProductExternalMapping
from modules.product_master.repository import normalize_alias


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _transaction_safe_match(
    self,
    session,
    organization_id: str,
    source: str,
    entity: str,
    row: Mapping[str, Any],
) -> tuple[str, float, str, str]:
    """Resolve cutover records without leaving the active staging transaction."""

    if entity == "vendor":
        name = _clean(row.get("name"))
        if not name:
            return "unmapped", 0.0, "", "Vendor name is missing."
        matches = list(
            session.scalars(
                select(TradePartner).where(
                    TradePartner.organization_id == organization_id,
                    func.lower(TradePartner.name) == name.casefold(),
                )
            )
        )
        if len(matches) == 1:
            return "auto_match", 1.0, str(matches[0].id), "Exact vendor name."
        if len(matches) > 1:
            return "conflict", 0.0, "", "Multiple vendor records share this name."
        return "unmapped", 0.0, "", "No exact vendor match."

    name = _clean(row.get("name") or row.get("product_name"))
    sku = _clean(row.get("sku"))
    upc = _clean(row.get("upc"))
    external = _clean(row.get("external_id"))
    candidates: dict[str, str] = {}

    if external:
        for product_id in session.scalars(
            select(ProductExternalMapping.product_id).where(
                ProductExternalMapping.organization_id == organization_id,
                ProductExternalMapping.system_name == source,
                ProductExternalMapping.external_id == external,
                ProductExternalMapping.active.is_(True),
            )
        ):
            candidates[str(product_id)] = "Exact external mapping."
    if sku:
        for product_id in session.scalars(
            select(Product.id).where(
                Product.organization_id == organization_id,
                func.lower(Product.sku) == sku.casefold(),
                Product.active.is_(True),
            )
        ):
            candidates[str(product_id)] = "Exact SKU."
    if upc:
        for product_id in session.scalars(
            select(Product.id).where(
                Product.organization_id == organization_id,
                Product.upc == upc,
                Product.active.is_(True),
            )
        ):
            candidates[str(product_id)] = "Exact UPC."
    if name:
        for product_id in session.scalars(
            select(Product.id).where(
                Product.organization_id == organization_id,
                func.lower(Product.name) == name.casefold(),
                Product.active.is_(True),
            )
        ):
            candidates[str(product_id)] = "Exact product name."
        normalized = normalize_alias(name)
        if normalized:
            for product_id in session.scalars(
                select(ProductAlias.product_id).where(
                    ProductAlias.organization_id == organization_id,
                    ProductAlias.normalized_alias == normalized,
                    ProductAlias.active.is_(True),
                )
            ):
                candidates[str(product_id)] = "Confirmed Product Master alias."

    if len(candidates) == 1:
        product_id, reason = next(iter(candidates.items()))
        return "auto_match", 1.0, product_id, reason
    if len(candidates) > 1:
        return "conflict", 0.0, "", "Exact identifiers resolve to different canonical products."

    # Advisory candidate lookup only. This deliberately never auto-commits and
    # stays on the caller's ORM session so a read cannot roll back staged rows.
    if name:
        normalized = normalize_alias(name)
        tokens = [token for token in normalized.split() if len(token) > 1]
        advisory_ids: set[str] = set()
        if tokens:
            # Two leading terms provide useful review candidates without pretending
            # that a fuzzy similarity score is authoritative.
            clauses = [func.lower(Product.name).like(f"%{token}%") for token in tokens[:2]]
            for product_id in session.scalars(
                select(Product.id)
                .where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                    and_(*clauses),
                )
                .limit(3)
            ):
                advisory_ids.add(str(product_id))
        if len(advisory_ids) == 1:
            return (
                "review_required",
                0.6,
                next(iter(advisory_ids)),
                "One non-exact Product Master candidate; human review required.",
            )

    return "unmapped", 0.0, "", "No deterministic canonical product match."


def install_transaction_safe_match(service_class):
    """Install the matcher once on the canonical MigrationCenterService class."""

    service_class._match = _transaction_safe_match
    return service_class
