"""Supplier portal staging service built on PartnerPortalAccess and TradePartner."""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any, Iterable

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Product, TradePartner, new_id, utc_now
from modules.operational_moats.models import PartnerPortalAccess
from modules.operational_moats.service import OperationalMoatService, _hash_token, _new_token

from .models import SupplierOffer, SupplierOfferLine, SupplierPortalGrant


DEFAULT_SUPPLIER_PERMISSIONS = frozenset({"offer:read", "offer:submit", "offer:revise", "offer:withdraw"})
BUYER_REVIEW_STATUSES = frozenset({"under_review", "accepted", "rejected"})


def _permissions(raw: str) -> frozenset[str]:
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = []
    return frozenset(str(value).strip().casefold() for value in parsed if str(value).strip())


def _permissions_json(values: Iterable[str]) -> str:
    normalized = sorted({str(value).strip().casefold() for value in values if str(value).strip()})
    return json.dumps(normalized, separators=(",", ":"))


class SupplierPortalService:
    """Stages supplier-originated buying data without mutating ERP ledgers."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def issue_supplier_access(
        self,
        *,
        organization_id: str,
        facility_id: str,
        partner_id: str,
        actor: str,
        label: str = "Supplier Portal",
        expires_days: int = 90,
        permissions: Iterable[str] | None = None,
    ) -> tuple[PartnerPortalAccess, SupplierPortalGrant, str]:
        """Issue the existing partner-portal token plus a supplier-only policy row."""

        requested_permissions = frozenset(permissions or DEFAULT_SUPPLIER_PERMISSIONS)
        if not requested_permissions or not requested_permissions.issubset(DEFAULT_SUPPLIER_PERMISSIONS):
            raise ValueError("Supplier portal permissions must use the reviewed supplier permission set.")
        with self._sessions.begin() as session:
            partner = session.get(TradePartner, partner_id)
            if not partner or partner.organization_id != organization_id or partner.partner_type not in {"vendor", "both"}:
                raise ValueError("A vendor trade partner is required for supplier portal access.")
            token = _new_token("dlp")
            access = PartnerPortalAccess(
                organization_id=organization_id,
                facility_id=facility_id,
                partner_id=partner_id,
                token_hash=_hash_token(token),
                label=str(label or "Supplier Portal").strip() or "Supplier Portal",
                created_by=str(actor or "").strip() or "system",
                expires_at=utc_now() + timedelta(days=max(1, min(int(expires_days), 365))),
            )
            session.add(access)
            session.flush()
            grant = SupplierPortalGrant(
                portal_access_id=access.id,
                organization_id=organization_id,
                facility_id=facility_id,
                partner_id=partner_id,
                permissions_json=_permissions_json(requested_permissions),
                created_by=str(actor or "").strip() or "system",
            )
            session.add(grant)
            session.flush()
            return access, grant, token

    def resolve_supplier_access(
        self,
        token: str,
        *,
        permission: str = "offer:read",
    ) -> tuple[PartnerPortalAccess, SupplierPortalGrant]:
        """Resolve the existing partner token and require its supplier policy."""

        access = OperationalMoatService(self.engine).resolve_partner_portal(token)
        with self._sessions() as session:
            grant = session.scalar(
                select(SupplierPortalGrant).where(SupplierPortalGrant.portal_access_id == access.id)
            )
            partner = session.get(TradePartner, access.partner_id)
            if (
                not grant
                or grant.organization_id != access.organization_id
                or grant.facility_id != access.facility_id
                or grant.partner_id != access.partner_id
                or not partner
                or partner.organization_id != access.organization_id
                or partner.partner_type not in {"vendor", "both"}
            ):
                raise ValueError("This partner portal token does not have supplier access.")
            required = str(permission or "").strip().casefold()
            if required and required not in _permissions(grant.permissions_json):
                raise ValueError("This supplier portal token does not allow the requested action.")
            return access, grant

    def submit_offer(
        self,
        *,
        access: PartnerPortalAccess,
        lines: list[dict[str, Any]],
        external_reference: str = "",
        valid_from: date | None = None,
        valid_until: date | None = None,
        promotion_terms: str = "",
        notes: str = "",
        lead_time_days: int | None = None,
        offer_group_id: str = "",
        revision: int = 1,
        supersedes_offer_id: str | None = None,
    ) -> SupplierOffer:
        """Persist one immutable supplier offer revision in review/staging state."""

        if not lines:
            raise ValueError("A supplier offer must contain at least one line.")
        if valid_from and valid_until and valid_until < valid_from:
            raise ValueError("Offer expiration cannot be before its effective date.")
        if lead_time_days is not None and int(lead_time_days) < 0:
            raise ValueError("Lead time cannot be negative.")

        with self._sessions.begin() as session:
            grant = session.scalar(select(SupplierPortalGrant).where(SupplierPortalGrant.portal_access_id == access.id))
            if not grant or "offer:submit" not in _permissions(grant.permissions_json):
                raise ValueError("Supplier portal access does not allow offer submission.")
            partner = session.get(TradePartner, access.partner_id)
            if not partner or partner.organization_id != access.organization_id or partner.partner_type not in {"vendor", "both"}:
                raise ValueError("The supplier trade partner is unavailable.")

            group_id = str(offer_group_id or "").strip() or new_id()
            offer = SupplierOffer(
                offer_group_id=group_id,
                revision=max(1, int(revision)),
                supersedes_offer_id=supersedes_offer_id,
                organization_id=access.organization_id,
                facility_id=access.facility_id,
                partner_id=access.partner_id,
                portal_access_id=access.id,
                status="submitted",
                external_reference=str(external_reference or "").strip(),
                valid_from=valid_from,
                valid_until=valid_until,
                promotion_terms=str(promotion_terms or "").strip(),
                notes=str(notes or "").strip(),
                lead_time_days=int(lead_time_days) if lead_time_days is not None else None,
                submitted_by=f"supplier_portal:{access.id}",
            )
            session.add(offer)
            session.flush()
            self._add_lines(session, offer, lines)
            session.flush()
            return offer

    def revise_offer(
        self,
        *,
        access: PartnerPortalAccess,
        offer_id: str,
        lines: list[dict[str, Any]],
        external_reference: str = "",
        valid_from: date | None = None,
        valid_until: date | None = None,
        promotion_terms: str = "",
        notes: str = "",
        lead_time_days: int | None = None,
    ) -> SupplierOffer:
        """Create a new immutable revision and supersede the prior supplier row."""

        if not lines:
            raise ValueError("A supplier offer revision must contain at least one line.")
        if valid_from and valid_until and valid_until < valid_from:
            raise ValueError("Offer expiration cannot be before its effective date.")
        with self._sessions.begin() as session:
            grant = session.scalar(select(SupplierPortalGrant).where(SupplierPortalGrant.portal_access_id == access.id))
            if not grant or "offer:revise" not in _permissions(grant.permissions_json):
                raise ValueError("Supplier portal access does not allow offer revision.")
            prior = session.get(SupplierOffer, offer_id)
            if (
                not prior
                or prior.organization_id != access.organization_id
                or prior.facility_id != access.facility_id
                or prior.partner_id != access.partner_id
                or prior.portal_access_id != access.id
            ):
                raise ValueError("Supplier offer was not found for this portal access.")
            if prior.status in {"withdrawn", "superseded", "expired"}:
                raise ValueError("This supplier offer revision can no longer be revised.")
            prior.status = "superseded"
            revision = SupplierOffer(
                offer_group_id=prior.offer_group_id,
                revision=prior.revision + 1,
                supersedes_offer_id=prior.id,
                organization_id=prior.organization_id,
                facility_id=prior.facility_id,
                partner_id=prior.partner_id,
                portal_access_id=access.id,
                status="submitted",
                external_reference=str(external_reference or prior.external_reference or "").strip(),
                valid_from=valid_from,
                valid_until=valid_until,
                promotion_terms=str(promotion_terms or "").strip(),
                notes=str(notes or "").strip(),
                lead_time_days=int(lead_time_days) if lead_time_days is not None else None,
                submitted_by=f"supplier_portal:{access.id}",
            )
            session.add(revision)
            session.flush()
            self._add_lines(session, revision, lines)
            session.flush()
            return revision

    def withdraw_offer(self, *, access: PartnerPortalAccess, offer_id: str) -> SupplierOffer:
        with self._sessions.begin() as session:
            grant = session.scalar(select(SupplierPortalGrant).where(SupplierPortalGrant.portal_access_id == access.id))
            if not grant or "offer:withdraw" not in _permissions(grant.permissions_json):
                raise ValueError("Supplier portal access does not allow offer withdrawal.")
            offer = session.get(SupplierOffer, offer_id)
            if (
                not offer
                or offer.organization_id != access.organization_id
                or offer.facility_id != access.facility_id
                or offer.partner_id != access.partner_id
                or offer.portal_access_id != access.id
            ):
                raise ValueError("Supplier offer was not found for this portal access.")
            if offer.status in {"accepted", "rejected", "withdrawn", "superseded", "expired"}:
                raise ValueError("This supplier offer can no longer be withdrawn.")
            offer.status = "withdrawn"
            offer.withdrawn_at = utc_now()
            return offer

    def review_offer(
        self,
        *,
        organization_id: str,
        facility_id: str,
        offer_id: str,
        status: str,
        actor: str,
    ) -> SupplierOffer:
        """Record buyer review state only; this method never creates a PO."""

        target = str(status or "").strip().casefold()
        if target not in BUYER_REVIEW_STATUSES:
            raise ValueError("Supplier offer review status must be under_review, accepted, or rejected.")
        with self._sessions.begin() as session:
            offer = session.get(SupplierOffer, offer_id)
            if not offer or offer.organization_id != organization_id or offer.facility_id != facility_id:
                raise ValueError("Supplier offer was not found in the active facility.")
            if offer.status in {"withdrawn", "superseded", "expired"}:
                raise ValueError("This supplier offer revision is no longer reviewable.")
            offer.status = target
            # Keep the human reviewer in the audit-facing notes without creating
            # purchase or inventory side effects in this staging service.
            reviewer_note = f"reviewed_by={str(actor or '').strip() or 'system'}"
            if reviewer_note not in offer.notes:
                offer.notes = (offer.notes + "\n" + reviewer_note).strip()
            return offer

    def list_offers(
        self,
        organization_id: str,
        facility_id: str,
        *,
        partner_id: str = "",
        current_only: bool = False,
        limit: int = 250,
    ) -> list[SupplierOffer]:
        with self._sessions() as session:
            stmt = select(SupplierOffer).where(
                SupplierOffer.organization_id == organization_id,
                SupplierOffer.facility_id == facility_id,
            )
            if partner_id:
                stmt = stmt.where(SupplierOffer.partner_id == partner_id)
            if current_only:
                stmt = stmt.where(SupplierOffer.status.notin_(("withdrawn", "superseded", "expired")))
            return list(session.scalars(stmt.order_by(SupplierOffer.submitted_at.desc()).limit(max(1, min(int(limit), 1000)))))

    def list_offer_lines(self, organization_id: str, offer_id: str) -> list[SupplierOfferLine]:
        with self._sessions() as session:
            offer = session.get(SupplierOffer, offer_id)
            if not offer or offer.organization_id != organization_id:
                raise ValueError("Supplier offer was not found.")
            return list(session.scalars(select(SupplierOfferLine).where(SupplierOfferLine.offer_id == offer_id).order_by(SupplierOfferLine.position)))

    @staticmethod
    def _add_lines(session, offer: SupplierOffer, lines: list[dict[str, Any]]) -> None:
        for position, raw in enumerate(lines, start=1):
            product_name = str(raw.get("product_name") or "").strip()
            if not product_name:
                raise ValueError(f"Supplier offer line {position} requires a product name.")
            available = float(raw.get("available_quantity") or 0.0)
            price = float(raw.get("unit_price") or 0.0)
            minimum = float(raw.get("minimum_order_quantity") or 0.0)
            if available < 0 or price < 0 or minimum < 0:
                raise ValueError(f"Supplier offer line {position} quantities and price cannot be negative.")
            product_id = str(raw.get("product_id") or "").strip() or None
            if product_id:
                product = session.get(Product, product_id)
                if not product or product.organization_id != offer.organization_id:
                    raise ValueError(f"Supplier offer line {position} references an invalid canonical product.")
            sample_status = str(raw.get("sample_status") or "none").strip().casefold()
            if sample_status not in {"none", "offered", "requested", "approved", "sent", "received", "declined"}:
                raise ValueError(f"Supplier offer line {position} has an unsupported sample status.")
            session.add(
                SupplierOfferLine(
                    offer_id=offer.id,
                    organization_id=offer.organization_id,
                    facility_id=offer.facility_id,
                    position=position,
                    product_id=product_id,
                    supplier_sku=str(raw.get("supplier_sku") or "").strip(),
                    product_name=product_name,
                    strain=str(raw.get("strain") or "").strip(),
                    form=str(raw.get("form") or "").strip(),
                    package_size=float(raw["package_size"]) if raw.get("package_size") not in (None, "") else None,
                    package_size_unit=str(raw.get("package_size_unit") or "").strip(),
                    available_quantity=available,
                    availability_unit=str(raw.get("availability_unit") or "unit").strip() or "unit",
                    unit_price=price,
                    price_basis=str(raw.get("price_basis") or "unit").strip().casefold() or "unit",
                    minimum_order_quantity=minimum,
                    minimum_order_unit=str(raw.get("minimum_order_unit") or "unit").strip() or "unit",
                    batch_lot_identifier=str(raw.get("batch_lot_identifier") or "").strip(),
                    coa_reference=str(raw.get("coa_reference") or "").strip(),
                    sample_status=sample_status,
                    promotion_terms=str(raw.get("promotion_terms") or "").strip(),
                    notes=str(raw.get("notes") or "").strip(),
                )
            )
