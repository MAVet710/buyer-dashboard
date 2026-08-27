"""Tenant-safe hosted storefront publishing and approval-gated wholesale order intake."""

from __future__ import annotations

from datetime import date
import json
import re
from typing import Any

from sqlalchemy import Engine, or_, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Product, TradePartner, utc_now
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository

from .models import CommerceStorefront, CommerceStorefrontOrderRequest, CommerceStorefrontProduct

_RESERVED_SUBDOMAINS = {"www", "api", "ops", "app", "admin", "beta", "support", "status", "mail", "store", "portal"}


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().casefold()).strip("-")
    if len(clean) < 2 or len(clean) > 63:
        raise ValueError("Storefront subdomain must be 2 to 63 letters, numbers, or hyphens.")
    if clean in _RESERVED_SUBDOMAINS:
        raise ValueError("That DoobieLogic subdomain is reserved.")
    return clean


class CommerceStorefrontService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def get_storefront(self, organization_id: str, facility_id: str) -> CommerceStorefront | None:
        with self._sessions() as session:
            return session.scalar(select(CommerceStorefront).where(
                CommerceStorefront.organization_id == organization_id,
                CommerceStorefront.facility_id == facility_id,
            ).order_by(CommerceStorefront.created_at.asc()))

    def upsert_storefront(self, *, organization_id: str, facility_id: str, actor: str, display_name: str, subdomain: str, headline: str = "Wholesale ordering", description: str = "", logo_url: str = "", hero_image_url: str = "", accent_color: str = "#8abf55", contact_email: str = "", order_instructions: str = "", published: bool = False) -> CommerceStorefront:
        clean_subdomain = _slug(subdomain)
        clean_name = str(display_name or "").strip()
        if not clean_name:
            raise ValueError("Storefront display name is required.")
        color = str(accent_color or "#8abf55").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Accent color must be a six-digit hex color such as #8abf55.")
        for value, label in ((logo_url, "Logo URL"), (hero_image_url, "Hero image URL")):
            if value and not str(value).strip().lower().startswith("https://"):
                raise ValueError(f"{label} must use HTTPS.")
        with self._sessions.begin() as session:
            row = session.scalar(select(CommerceStorefront).where(
                CommerceStorefront.organization_id == organization_id,
                CommerceStorefront.facility_id == facility_id,
            ).order_by(CommerceStorefront.created_at.asc()))
            collision = session.scalar(select(CommerceStorefront).where(
                CommerceStorefront.subdomain == clean_subdomain,
                CommerceStorefront.id != (row.id if row else ""),
            ))
            if collision:
                raise ValueError("That DoobieLogic subdomain is already in use.")
            if row is None:
                row = CommerceStorefront(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    slug=clean_subdomain,
                    subdomain=clean_subdomain,
                    display_name=clean_name,
                    created_by=actor,
                    updated_by=actor,
                )
                session.add(row)
            row.slug = clean_subdomain
            row.subdomain = clean_subdomain
            row.display_name = clean_name
            row.headline = str(headline or "Wholesale ordering").strip()
            row.description = str(description or "").strip()
            row.logo_url = str(logo_url or "").strip()
            row.hero_image_url = str(hero_image_url or "").strip()
            row.accent_color = color.lower()
            row.contact_email = str(contact_email or "").strip()
            row.order_instructions = str(order_instructions or "").strip()
            row.published = bool(published)
            row.updated_by = actor
            session.flush()
            return row

    def list_catalog_options(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        repo = ComanRepository(self.engine)
        products = repo.list_products(organization_id)
        lots = repo.list_inventory_lots(organization_id, facility_id)
        balances: dict[str, float] = {}
        for lot in lots:
            if lot.status in {"available", "released"}:
                balances[lot.product_id] = balances.get(lot.product_id, 0.0) + max(0.0, repo.inventory_balance(organization_id, lot.id))
        return [{
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "unit": product.base_unit,
            "available": balances.get(product.id, 0.0),
            "suggested_price_usd": float(product.retail_price or 0.0),
        } for product in products if product.active]

    def set_products(self, *, organization_id: str, facility_id: str, actor: str, products: list[dict[str, Any]]) -> list[CommerceStorefrontProduct]:
        storefront = self.get_storefront(organization_id, facility_id)
        if not storefront:
            raise ValueError("Create the storefront before selecting products.")
        with self._sessions.begin() as session:
            current = {row.product_id: row for row in session.scalars(select(CommerceStorefrontProduct).where(CommerceStorefrontProduct.storefront_id == storefront.id))}
            wanted: set[str] = set()
            for index, raw in enumerate(products):
                product_id = str(raw.get("product_id") or "")
                product = session.get(Product, product_id)
                if not product or product.organization_id != organization_id or not product.active:
                    raise ValueError("Every storefront listing must use an active organization product.")
                price = float(raw.get("price_usd") or 0.0)
                minimum = float(raw.get("minimum_quantity") or 1.0)
                case = float(raw.get("case_quantity") or 1.0)
                if price < 0 or minimum <= 0 or case <= 0:
                    raise ValueError("Storefront price cannot be negative and order quantities must be greater than zero.")
                wanted.add(product_id)
                row = current.get(product_id)
                if row is None:
                    row = CommerceStorefrontProduct(organization_id=organization_id, storefront_id=storefront.id, product_id=product_id)
                    session.add(row)
                row.price_usd = price
                row.minimum_quantity = minimum
                row.case_quantity = case
                row.featured = bool(raw.get("featured", False))
                row.active = bool(raw.get("active", True))
                row.sort_order = int(raw.get("sort_order") if raw.get("sort_order") is not None else index)
            for product_id, row in current.items():
                if product_id not in wanted:
                    row.active = False
            session.flush()
            return list(session.scalars(select(CommerceStorefrontProduct).where(CommerceStorefrontProduct.storefront_id == storefront.id).order_by(CommerceStorefrontProduct.sort_order, CommerceStorefrontProduct.created_at)))

    def admin_snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        storefront = self.get_storefront(organization_id, facility_id)
        if not storefront:
            return {"storefront": None, "products": [], "pending_orders": []}
        with self._sessions() as session:
            listings = list(session.scalars(select(CommerceStorefrontProduct).where(CommerceStorefrontProduct.storefront_id == storefront.id).order_by(CommerceStorefrontProduct.sort_order, CommerceStorefrontProduct.created_at)))
            products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == organization_id))}
        return {
            "storefront": self._storefront_dict(storefront),
            "products": [self._listing_dict(row, products.get(row.product_id)) for row in listings],
            "pending_orders": self.list_order_requests(organization_id, facility_id),
        }

    def resolve_public(self, slug: str) -> CommerceStorefront:
        clean = _slug(slug)
        with self._sessions() as session:
            row = session.scalar(select(CommerceStorefront).where(or_(CommerceStorefront.subdomain == clean, CommerceStorefront.slug == clean), CommerceStorefront.published.is_(True)))
            if not row:
                raise ValueError("Storefront was not found or is not published.")
            return row

    def public_catalog(self, slug: str) -> dict[str, Any]:
        storefront = self.resolve_public(slug)
        options = {row["product_id"]: row for row in self.list_catalog_options(storefront.organization_id, storefront.facility_id)}
        with self._sessions() as session:
            listings = list(session.scalars(select(CommerceStorefrontProduct).where(
                CommerceStorefrontProduct.storefront_id == storefront.id,
                CommerceStorefrontProduct.active.is_(True),
            ).order_by(CommerceStorefrontProduct.featured.desc(), CommerceStorefrontProduct.sort_order, CommerceStorefrontProduct.created_at)))
            products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == storefront.organization_id))}
        catalog = []
        for listing in listings:
            product = products.get(listing.product_id)
            option = options.get(listing.product_id)
            if not product or not option or float(option["available"]) <= 0:
                continue
            catalog.append({
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "unit": product.base_unit,
                "available": float(option["available"]),
                "price_usd": float(listing.price_usd),
                "minimum_quantity": float(listing.minimum_quantity),
                "case_quantity": float(listing.case_quantity),
                "featured": bool(listing.featured),
            })
        return {"storefront": self._storefront_dict(storefront), "catalog": catalog}

    def submit_order_request(self, *, slug: str, buyer_company: str, buyer_contact: str, buyer_email: str, lines: list[dict[str, Any]], buyer_license: str = "", buyer_phone: str = "", requested_delivery_date: date | None = None, purchase_order_reference: str = "", notes: str = "") -> CommerceStorefrontOrderRequest:
        company = str(buyer_company or "").strip()
        contact = str(buyer_contact or "").strip()
        email = str(buyer_email or "").strip()
        if not company or not contact or "@" not in email:
            raise ValueError("Business name, contact name, and a valid email are required.")
        catalog = self.public_catalog(slug)
        storefront_data = catalog["storefront"]
        by_product = {row["product_id"]: row for row in catalog["catalog"]}
        if not lines:
            raise ValueError("Add at least one product to the order request.")
        snapshots = []
        subtotal = 0.0
        for raw in lines:
            item = by_product.get(str(raw.get("product_id") or ""))
            if not item:
                raise ValueError("A requested product is not currently available on this storefront.")
            quantity = float(raw.get("quantity") or 0.0)
            if quantity < item["minimum_quantity"] or quantity > item["available"]:
                raise ValueError(f"Quantity for {item['name']} must be between {item['minimum_quantity']:g} and {item['available']:g} {item['unit']}.")
            case = float(item["case_quantity"] or 1.0)
            multiple = quantity / case
            if abs(multiple - round(multiple)) > 1e-7:
                raise ValueError(f"{item['name']} must be ordered in multiples of {case:g} {item['unit']}.")
            line_total = quantity * float(item["price_usd"])
            subtotal += line_total
            snapshots.append({**item, "quantity": quantity, "line_total": line_total})
        with self._sessions.begin() as session:
            storefront = session.get(CommerceStorefront, storefront_data["id"])
            row = CommerceStorefrontOrderRequest(
                organization_id=storefront.organization_id,
                facility_id=storefront.facility_id,
                storefront_id=storefront.id,
                buyer_company=company,
                buyer_license=str(buyer_license or "").strip(),
                buyer_contact=contact,
                buyer_email=email,
                buyer_phone=str(buyer_phone or "").strip(),
                purchase_order_reference=str(purchase_order_reference or "").strip(),
                requested_delivery_date=requested_delivery_date,
                notes=str(notes or "").strip(),
                lines_json=_json(snapshots),
                estimated_subtotal=subtotal,
            )
            session.add(row)
            session.flush()
            return row

    def list_order_requests(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = list(session.scalars(select(CommerceStorefrontOrderRequest).where(
                CommerceStorefrontOrderRequest.organization_id == organization_id,
                CommerceStorefrontOrderRequest.facility_id == facility_id,
            ).order_by(CommerceStorefrontOrderRequest.created_at.desc()).limit(250)))
        return [self._request_dict(row) for row in rows]

    def approve_order_request(self, *, organization_id: str, facility_id: str, request_id: str, actor: str, review_note: str = "") -> dict[str, Any]:
        with self._sessions() as session:
            request = session.get(CommerceStorefrontOrderRequest, request_id)
            if not request or request.organization_id != organization_id or request.facility_id != facility_id:
                raise ValueError("Storefront order request was not found in this facility.")
            if request.status != "submitted":
                raise ValueError("Only submitted storefront orders can be approved.")
            storefront = session.get(CommerceStorefront, request.storefront_id)
            original_lines = _load(request.lines_json, [])
        current = {row["product_id"]: row for row in self.public_catalog(storefront.slug)["catalog"]}
        order_lines = []
        for original in original_lines:
            item = current.get(original.get("product_id"))
            quantity = float(original.get("quantity") or 0.0)
            if not item or quantity > float(item["available"]):
                raise ValueError(f"Inventory changed for {original.get('name') or 'a requested product'}. Review the request before approval.")
            order_lines.append({
                "product_id": item["product_id"],
                "quantity": quantity,
                "unit": item["unit"],
                "unit_price": float(original.get("price_usd") or item["price_usd"]),
                "description": item["name"],
            })
        partner = self._resolve_or_create_partner(request, actor)
        order_number = f"WEB-{utc_now().strftime('%Y%m%d%H%M%S')}-{request.id[:6].upper()}"
        order = CommercialRepository(self.engine).create_order(
            organization_id=organization_id,
            facility_id=facility_id,
            partner_id=partner.id,
            order_number=order_number,
            order_type="sales",
            order_date=date.today(),
            due_date=request.requested_delivery_date,
            lines=order_lines,
            actor=actor,
            external_reference=request.purchase_order_reference,
            notes=(request.notes + "\n" if request.notes else "") + f"Approved from hosted storefront {storefront.subdomain}.doobielogic.io request {request.id}.",
        )
        with self._sessions.begin() as session:
            row = session.get(CommerceStorefrontOrderRequest, request.id)
            if row.status != "submitted":
                raise ValueError("Storefront request changed while approval was in progress.")
            row.status = "approved"
            row.partner_id = partner.id
            row.commercial_order_id = order.id
            row.reviewed_by = actor
            row.reviewed_at = utc_now()
            row.review_note = str(review_note or "").strip()
        return {"request": self._request_dict(row), "order_id": order.id, "order_number": order.order_number, "order_status": order.status}

    def reject_order_request(self, *, organization_id: str, facility_id: str, request_id: str, actor: str, review_note: str = "") -> dict[str, Any]:
        with self._sessions.begin() as session:
            row = session.get(CommerceStorefrontOrderRequest, request_id)
            if not row or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("Storefront order request was not found in this facility.")
            if row.status != "submitted":
                raise ValueError("Only submitted storefront orders can be rejected.")
            row.status = "rejected"
            row.reviewed_by = actor
            row.reviewed_at = utc_now()
            row.review_note = str(review_note or "").strip()
            session.flush()
            return self._request_dict(row)

    def _resolve_or_create_partner(self, request: CommerceStorefrontOrderRequest, actor: str) -> TradePartner:
        with self._sessions() as session:
            stmt = select(TradePartner).where(TradePartner.organization_id == request.organization_id, TradePartner.active.is_(True))
            if request.buyer_license:
                stmt = stmt.where(or_(TradePartner.license_or_registration == request.buyer_license, TradePartner.name == request.buyer_company))
            else:
                stmt = stmt.where(TradePartner.name == request.buyer_company)
            partner = session.scalar(stmt.order_by(TradePartner.created_at.asc()))
            if partner:
                if partner.partner_type not in {"customer", "both"}:
                    raise ValueError("The matching trade partner is not configured as a customer.")
                return partner
        return CommercialRepository(self.engine).create_trade_partner(
            request.organization_id,
            name=request.buyer_company,
            partner_type="customer",
            actor=actor,
            license_or_registration=request.buyer_license,
            contact_name=request.buyer_contact,
            contact_email=request.buyer_email,
            contact_phone=request.buyer_phone,
        )

    @staticmethod
    def _storefront_dict(row: CommerceStorefront) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "facility_id": row.facility_id,
            "slug": row.slug,
            "subdomain": row.subdomain,
            "url": f"https://{row.subdomain}.doobielogic.io",
            "display_name": row.display_name,
            "headline": row.headline,
            "description": row.description,
            "logo_url": row.logo_url,
            "hero_image_url": row.hero_image_url,
            "accent_color": row.accent_color,
            "contact_email": row.contact_email,
            "order_instructions": row.order_instructions,
            "published": row.published,
        }

    @staticmethod
    def _listing_dict(row: CommerceStorefrontProduct, product: Product | None) -> dict[str, Any]:
        return {
            "id": row.id,
            "product_id": row.product_id,
            "sku": product.sku if product else "",
            "name": product.name if product else "Unknown product",
            "unit": product.base_unit if product else "unit",
            "price_usd": float(row.price_usd),
            "minimum_quantity": float(row.minimum_quantity),
            "case_quantity": float(row.case_quantity),
            "featured": bool(row.featured),
            "active": bool(row.active),
            "sort_order": int(row.sort_order),
        }

    @staticmethod
    def _request_dict(row: CommerceStorefrontOrderRequest) -> dict[str, Any]:
        return {
            "id": row.id,
            "storefront_id": row.storefront_id,
            "buyer_company": row.buyer_company,
            "buyer_license": row.buyer_license,
            "buyer_contact": row.buyer_contact,
            "buyer_email": row.buyer_email,
            "buyer_phone": row.buyer_phone,
            "purchase_order_reference": row.purchase_order_reference,
            "requested_delivery_date": row.requested_delivery_date,
            "notes": row.notes,
            "lines": _load(row.lines_json, []),
            "estimated_subtotal": float(row.estimated_subtotal),
            "status": row.status,
            "partner_id": row.partner_id,
            "commercial_order_id": row.commercial_order_id,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "review_note": row.review_note,
            "created_at": row.created_at,
        }
