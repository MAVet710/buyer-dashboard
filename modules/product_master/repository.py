"""Transactional repository for the canonical Buyer Dash Product Master."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Product, TradePartner, utc_now

from .models import (
    ProductAlias,
    ProductExternalMapping,
    ProductMasterProfile,
    ProductValueEvent,
    ProductVendorLink,
)


VALUE_TYPES = {"unit_cost", "landed_cost", "retail_price", "wholesale_price"}


def normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


class ProductMasterRepository:
    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _product(session, organization_id: str, product_id: str) -> Product:
        product = session.get(Product, product_id)
        if not product or product.organization_id != organization_id:
            raise ValueError("Product was not found in this organization.")
        return product

    @staticmethod
    def _vendor(session, organization_id: str, partner_id: str) -> TradePartner:
        partner = session.get(TradePartner, partner_id)
        if not partner or partner.organization_id != organization_id:
            raise ValueError("Vendor was not found in this organization.")
        if partner.partner_type not in {"vendor", "both"}:
            raise ValueError("The selected trade partner is not configured as a vendor.")
        return partner

    def update_profile(
        self,
        organization_id: str,
        product_id: str,
        *,
        actor: str,
        brand: str = "",
        category: str = "",
        subcategory: str = "",
        strain: str = "",
        manufacturer: str = "",
        product_format: str = "",
        description: str = "",
        retail_enabled: bool | None = None,
        production_enabled: bool | None = None,
    ) -> ProductMasterProfile:
        fields = {
            "brand": str(brand or "").strip(),
            "category": str(category or "").strip(),
            "subcategory": str(subcategory or "").strip(),
            "strain": str(strain or "").strip(),
            "manufacturer": str(manufacturer or "").strip(),
            "product_format": str(product_format or "").strip(),
            "description": str(description or "").strip(),
        }
        if retail_enabled is not None:
            fields["retail_enabled"] = bool(retail_enabled)
        if production_enabled is not None:
            fields["production_enabled"] = bool(production_enabled)
        with self._session_factory.begin() as session:
            self._product(session, organization_id, product_id)
            profile = session.get(ProductMasterProfile, product_id)
            before = {}
            if profile is None:
                profile = ProductMasterProfile(
                    organization_id=organization_id,
                    product_id=product_id,
                    **fields,
                )
                session.add(profile)
                action = "profile_created"
            else:
                if profile.organization_id != organization_id:
                    raise ValueError("Product profile belongs to another organization.")
                before = {key: getattr(profile, key) for key in fields}
                for key, value in fields.items():
                    setattr(profile, key, value)
                action = "profile_updated"
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    entity_type="product",
                    entity_id=product_id,
                    action=action,
                    actor=str(actor or "system"),
                    changes_json=json.dumps({"before": before, "after": fields}, sort_keys=True),
                )
            )
        return profile

    def link_vendor(
        self,
        organization_id: str,
        product_id: str,
        partner_id: str,
        *,
        actor: str,
        vendor_sku: str = "",
        is_primary: bool = False,
        lead_time_days: int = 0,
        minimum_order_quantity: float = 0,
        case_pack: float = 0,
        active: bool = True,
    ) -> ProductVendorLink:
        if int(lead_time_days) < 0:
            raise ValueError("Vendor lead time cannot be negative.")
        if float(minimum_order_quantity) < 0 or float(case_pack) < 0:
            raise ValueError("Vendor MOQ and case pack cannot be negative.")
        with self._session_factory.begin() as session:
            self._product(session, organization_id, product_id)
            self._vendor(session, organization_id, partner_id)
            existing = session.scalar(
                select(ProductVendorLink).where(
                    ProductVendorLink.organization_id == organization_id,
                    ProductVendorLink.product_id == product_id,
                    ProductVendorLink.partner_id == partner_id,
                )
            )
            if is_primary:
                for row in session.scalars(
                    select(ProductVendorLink).where(
                        ProductVendorLink.organization_id == organization_id,
                        ProductVendorLink.product_id == product_id,
                        ProductVendorLink.is_primary.is_(True),
                    )
                ):
                    row.is_primary = False
            if existing is None:
                existing = ProductVendorLink(
                    organization_id=organization_id,
                    product_id=product_id,
                    partner_id=partner_id,
                )
                session.add(existing)
            existing.vendor_sku = str(vendor_sku or "").strip()
            existing.is_primary = bool(is_primary)
            existing.lead_time_days = int(lead_time_days)
            existing.minimum_order_quantity = float(minimum_order_quantity)
            existing.case_pack = float(case_pack)
            existing.active = bool(active)
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    entity_type="product",
                    entity_id=product_id,
                    action="vendor_linked",
                    actor=str(actor or "system"),
                    changes_json=json.dumps(
                        {
                            "partner_id": partner_id,
                            "vendor_sku": existing.vendor_sku,
                            "is_primary": existing.is_primary,
                            "lead_time_days": existing.lead_time_days,
                            "minimum_order_quantity": existing.minimum_order_quantity,
                            "case_pack": existing.case_pack,
                            "active": existing.active,
                        },
                        sort_keys=True,
                    ),
                )
            )
        return existing

    def map_external(
        self,
        organization_id: str,
        product_id: str,
        *,
        system_name: str,
        external_id: str,
        actor: str,
        external_name: str = "",
        active: bool = True,
    ) -> ProductExternalMapping:
        system = str(system_name or "").strip().casefold()
        external = str(external_id or "").strip()
        if not system or not external:
            raise ValueError("External system and external product ID are required.")
        with self._session_factory.begin() as session:
            self._product(session, organization_id, product_id)
            mapped = session.scalar(
                select(ProductExternalMapping).where(
                    ProductExternalMapping.organization_id == organization_id,
                    ProductExternalMapping.system_name == system,
                    ProductExternalMapping.external_id == external,
                )
            )
            if mapped and mapped.product_id != product_id:
                raise ValueError("That external product is already mapped to a different Buyer Dash product.")
            if mapped is None:
                mapped = ProductExternalMapping(
                    organization_id=organization_id,
                    product_id=product_id,
                    system_name=system,
                    external_id=external,
                )
                session.add(mapped)
            mapped.external_name = str(external_name or "").strip()
            mapped.active = bool(active)
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    entity_type="product",
                    entity_id=product_id,
                    action="external_mapped",
                    actor=str(actor or "system"),
                    changes_json=json.dumps(
                        {"system_name": system, "external_id": external, "external_name": mapped.external_name},
                        sort_keys=True,
                    ),
                )
            )
        return mapped

    def add_alias(
        self,
        organization_id: str,
        product_id: str,
        alias: str,
        *,
        actor: str,
        source: str = "manual",
    ) -> ProductAlias:
        raw = str(alias or "").strip()
        normalized = normalize_alias(raw)
        if not normalized:
            raise ValueError("A product alias is required.")
        with self._session_factory.begin() as session:
            self._product(session, organization_id, product_id)
            existing = session.scalar(
                select(ProductAlias).where(
                    ProductAlias.organization_id == organization_id,
                    ProductAlias.normalized_alias == normalized,
                )
            )
            if existing and existing.product_id != product_id:
                raise ValueError("That alias already resolves to a different Buyer Dash product.")
            if existing is None:
                existing = ProductAlias(
                    organization_id=organization_id,
                    product_id=product_id,
                    alias=raw,
                    normalized_alias=normalized,
                    source=str(source or "manual").strip(),
                )
                session.add(existing)
            else:
                existing.alias = raw
                existing.source = str(source or existing.source).strip()
                existing.active = True
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    entity_type="product",
                    entity_id=product_id,
                    action="alias_added",
                    actor=str(actor or "system"),
                    changes_json=json.dumps({"alias": raw, "source": existing.source}, sort_keys=True),
                )
            )
        return existing

    def resolve_alias(self, organization_id: str, alias: str) -> Product | None:
        normalized = normalize_alias(alias)
        if not normalized:
            return None
        with self._session_factory() as session:
            product_id = session.scalar(
                select(ProductAlias.product_id).where(
                    ProductAlias.organization_id == organization_id,
                    ProductAlias.normalized_alias == normalized,
                    ProductAlias.active.is_(True),
                )
            )
            if not product_id:
                return None
            return session.get(Product, product_id)

    def record_value(
        self,
        organization_id: str,
        product_id: str,
        *,
        value_type: str,
        amount: float,
        actor: str,
        partner_id: str | None = None,
        currency: str = "USD",
        source: str = "manual",
        source_reference: str = "",
        effective_at: datetime | None = None,
    ) -> ProductValueEvent:
        kind = str(value_type or "").strip().casefold()
        if kind not in VALUE_TYPES:
            raise ValueError("Unsupported product value type.")
        if float(amount) < 0:
            raise ValueError("Product value cannot be negative.")
        with self._session_factory.begin() as session:
            product = self._product(session, organization_id, product_id)
            if partner_id:
                self._vendor(session, organization_id, partner_id)
            previous: float | None
            if kind == "unit_cost":
                previous = float(product.unit_cost or 0)
                product.unit_cost = float(amount)
            elif kind == "retail_price":
                previous = float(product.retail_price or 0)
                product.retail_price = float(amount)
            else:
                previous = session.scalar(
                    select(ProductValueEvent.amount)
                    .where(
                        ProductValueEvent.organization_id == organization_id,
                        ProductValueEvent.product_id == product_id,
                        ProductValueEvent.value_type == kind,
                    )
                    .order_by(ProductValueEvent.effective_at.desc())
                    .limit(1)
                )
                previous = float(previous) if previous is not None else None
            event = ProductValueEvent(
                organization_id=organization_id,
                product_id=product_id,
                partner_id=partner_id or None,
                value_type=kind,
                amount=float(amount),
                previous_amount=previous,
                currency=str(currency or "USD").strip().upper(),
                source=str(source or "manual").strip(),
                source_reference=str(source_reference or "").strip(),
                actor=str(actor or "system"),
                effective_at=effective_at or utc_now(),
            )
            session.add(event)
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    entity_type="product",
                    entity_id=product_id,
                    action="value_recorded",
                    actor=str(actor or "system"),
                    changes_json=json.dumps(
                        {"value_type": kind, "previous_amount": previous, "amount": float(amount), "currency": event.currency},
                        sort_keys=True,
                    ),
                )
            )
        return event

    def snapshot(self, organization_id: str, product_id: str, *, history_limit: int = 50) -> dict[str, Any]:
        with self._session_factory() as session:
            product = self._product(session, organization_id, product_id)
            profile = session.get(ProductMasterProfile, product_id)
            vendor_rows = list(
                session.scalars(
                    select(ProductVendorLink)
                    .where(
                        ProductVendorLink.organization_id == organization_id,
                        ProductVendorLink.product_id == product_id,
                        ProductVendorLink.active.is_(True),
                    )
                    .order_by(ProductVendorLink.is_primary.desc(), ProductVendorLink.created_at)
                )
            )
            partners = {
                row.id: row
                for row in session.scalars(
                    select(TradePartner).where(
                        TradePartner.id.in_([link.partner_id for link in vendor_rows])
                    )
                )
            } if vendor_rows else {}
            mappings = list(
                session.scalars(
                    select(ProductExternalMapping)
                    .where(
                        ProductExternalMapping.organization_id == organization_id,
                        ProductExternalMapping.product_id == product_id,
                        ProductExternalMapping.active.is_(True),
                    )
                    .order_by(ProductExternalMapping.system_name, ProductExternalMapping.external_id)
                )
            )
            aliases = list(
                session.scalars(
                    select(ProductAlias)
                    .where(
                        ProductAlias.organization_id == organization_id,
                        ProductAlias.product_id == product_id,
                        ProductAlias.active.is_(True),
                    )
                    .order_by(ProductAlias.alias)
                )
            )
            history = list(
                session.scalars(
                    select(ProductValueEvent)
                    .where(
                        ProductValueEvent.organization_id == organization_id,
                        ProductValueEvent.product_id == product_id,
                    )
                    .order_by(ProductValueEvent.effective_at.desc())
                    .limit(max(1, min(int(history_limit), 500)))
                )
            )
            return {
                "product": product,
                "profile": profile,
                "vendors": [
                    {"link": link, "partner": partners.get(link.partner_id)} for link in vendor_rows
                ],
                "mappings": mappings,
                "aliases": aliases,
                "value_history": history,
            }
