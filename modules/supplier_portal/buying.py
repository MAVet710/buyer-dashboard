"""Buyer-side comparison and governed PO proposal flow for supplier offers."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Product, TradePartner
from modules.data_hub_repository import DataHubRepository
from modules.doobie_actions.service import DoobieActionService
from services.market_data import build_market_intelligence
from services.market_data.market_intelligence import normalize_category
from services.web_buyer_parity import build_forecast, exact_buyer_intelligence, read_tabular_bytes, records

from .models import SupplierOffer, SupplierOfferLine


_INVENTORY_KEYS = ("inventory", "sandbox_buyer_inventory")
_SALES_KEYS = ("product_sales", "sandbox_buyer_sales", "sandbox_delivery_sales")
_LINEAGE_KEY = "supplier_lineage"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _pick_source(sources, keys):
    by_key = {row.dataset_key: row for row in sources}
    return next((by_key[key] for key in keys if key in by_key), None)


def supplier_lineage_note(payload: dict[str, Any]) -> str:
    """Serialize source lineage into the existing commercial-order line notes."""

    return json.dumps({_LINEAGE_KEY: payload}, sort_keys=True, separators=(",", ":"), default=str)


def parse_supplier_lineage_note(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    lineage = payload.get(_LINEAGE_KEY) if isinstance(payload, dict) else None
    return dict(lineage) if isinstance(lineage, dict) else {}


class SupplierBuyingService:
    """Compares staged supplier data and proposes, but never directly writes, POs."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _freshness(offer: SupplierOffer, stale_after_days: int) -> dict[str, Any]:
        today = date.today()
        submitted = offer.submitted_at.date() if offer.submitted_at else today
        age_days = max(0, (today - submitted).days)
        expired = offer.status == "expired" or bool(offer.valid_until and offer.valid_until < today)
        future = bool(offer.valid_from and offer.valid_from > today)
        stale = bool(not expired and not future and offer.valid_until is None and age_days > stale_after_days)
        if expired:
            state = "expired"
        elif future:
            state = "not_yet_effective"
        elif stale:
            state = "stale"
        else:
            state = "current"
        return {
            "state": state,
            "age_days": age_days,
            "stale_after_days": stale_after_days,
            "valid_from": offer.valid_from,
            "valid_until": offer.valid_until,
        }

    def _buyer_context(self, organization_id: str, facility_id: str, lookback_days: int) -> dict[str, Any]:
        try:
            sources = DataHubRepository(self.engine).list_active_sources(organization_id, facility_id)
            inventory_source = _pick_source(sources, _INVENTORY_KEYS)
            sales_source = _pick_source(sources, _SALES_KEYS)
            if inventory_source is None or sales_source is None:
                return {
                    "status": "unavailable",
                    "message": "Active Inventory and Product Sales sources are required for internal Buyer Intelligence comparison.",
                    "by_category": [],
                    "by_product": [],
                    "purchase_priorities": [],
                }
            inventory = read_tabular_bytes(inventory_source.payload, inventory_source.filename)
            sales = read_tabular_bytes(sales_source.payload, sales_source.filename)
            _detail, product, _inventory_normalized, sales_normalized = build_forecast(
                inventory,
                sales,
                doh_threshold=21,
                velocity_adjustment=1.0,
                sales_period_days=lookback_days,
            )
            result = exact_buyer_intelligence(product, sales_normalized, lookback_days)
            return {
                "status": "available",
                "summary": result["summary"],
                "by_category": records(result["by_category"], limit=100),
                "by_product": records(result["by_product"], limit=1000),
                "purchase_priorities": records(result["purchase_priorities"], limit=500),
                "sources": {
                    "inventory": inventory_source.filename,
                    "sales": sales_source.filename,
                },
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "message": "Internal Buyer Intelligence could not be calculated from the active data sources.",
                "error_type": type(exc).__name__,
                "by_category": [],
                "by_product": [],
                "purchase_priorities": [],
            }

    def _market_context(self, buyer: dict[str, Any], lookback_days: int) -> dict[str, Any]:
        return build_market_intelligence(
            store_category_rows=list(buyer.get("by_category") or []),
            store_product_rows=list(buyer.get("by_product") or []),
            lookback_days=lookback_days,
        )

    def compare_offer(
        self,
        organization_id: str,
        facility_id: str,
        offer_id: str,
        *,
        lookback_days: int = 60,
        stale_after_days: int = 14,
    ) -> dict[str, Any]:
        lookback_days = max(14, min(int(lookback_days), 120))
        stale_after_days = max(1, min(int(stale_after_days), 90))
        with self._sessions() as session:
            offer = session.get(SupplierOffer, offer_id)
            if not offer or offer.organization_id != organization_id or offer.facility_id != facility_id:
                raise ValueError("Supplier offer was not found in the active facility.")
            partner = session.get(TradePartner, offer.partner_id)
            lines = list(
                session.scalars(
                    select(SupplierOfferLine)
                    .where(SupplierOfferLine.offer_id == offer.id)
                    .order_by(SupplierOfferLine.position)
                )
            )
            product_ids = {line.product_id for line in lines if line.product_id}
            products = {
                row.id: row
                for row in session.scalars(select(Product).where(Product.id.in_(product_ids)))
            } if product_ids else {}

        buyer = self._buyer_context(organization_id, facility_id, lookback_days)
        try:
            market = self._market_context(buyer, lookback_days)
        except Exception as exc:
            market = {
                "status": "unavailable",
                "message": "Massachusetts market reference is temporarily unavailable.",
                "error_type": type(exc).__name__,
                "categories": [],
            }

        buyer_products = {
            _norm(row.get("product_name")): row
            for row in buyer.get("by_product") or []
            if _text(row.get("product_name"))
        }
        buyer_categories = {
            _norm(normalize_category(row.get("category"))): row
            for row in buyer.get("by_category") or []
            if _text(row.get("category"))
        }
        market_categories = {
            _norm(normalize_category(row.get("category"))): row
            for row in market.get("categories") or []
            if _text(row.get("category"))
        }

        comparisons = []
        for line in lines:
            product = products.get(line.product_id) if line.product_id else None
            match_name = _text(product.name if product else line.product_name)
            category = normalize_category(line.form or (product.item_type if product else ""))
            comparisons.append(
                {
                    "line_id": line.id,
                    "position": line.position,
                    "product_id": line.product_id,
                    "supplier_sku": line.supplier_sku,
                    "product_name": line.product_name,
                    "canonical_product_name": product.name if product else None,
                    "category": category,
                    "availability": {
                        "quantity": line.available_quantity,
                        "unit": line.availability_unit,
                        "minimum_order_quantity": line.minimum_order_quantity,
                        "minimum_order_unit": line.minimum_order_unit,
                    },
                    "quote": {
                        "unit_price": line.unit_price,
                        "price_basis": line.price_basis,
                        "wholesale_only": True,
                    },
                    "coa_reference": line.coa_reference,
                    "batch_lot_identifier": line.batch_lot_identifier,
                    "sample_status": line.sample_status,
                    "buyer_product": buyer_products.get(_norm(match_name)),
                    "buyer_category": buyer_categories.get(_norm(category)),
                    "ma_market_category": market_categories.get(_norm(category)),
                }
            )

        return {
            "offer": {
                "id": offer.id,
                "offer_group_id": offer.offer_group_id,
                "revision": offer.revision,
                "status": offer.status,
                "partner_id": offer.partner_id,
                "supplier_name": partner.name if partner else "",
                "external_reference": offer.external_reference,
                "submitted_at": offer.submitted_at,
                "freshness": self._freshness(offer, stale_after_days),
            },
            "buyer_intelligence": {
                key: value for key, value in buyer.items() if key not in {"by_category", "by_product", "purchase_priorities"}
            },
            "ma_market_reference": {
                key: value for key, value in market.items() if key != "categories"
            },
            "price_context": {
                "rule": "Supplier wholesale quote is not directly compared to Massachusetts retail dollars-per-gram pricing.",
                "basis": "wholesale_quote",
            },
            "lines": comparisons,
        }

    def propose_purchase_order(
        self,
        *,
        organization_id: str,
        facility_id: str,
        offer_id: str,
        selections: list[dict[str, Any]],
        actor: str,
        due_date: date | None = None,
        order_number: str = "",
        stale_after_days: int = 14,
    ):
        if not selections:
            raise ValueError("Select at least one supplier offer line for the purchase order proposal.")
        selected_quantities: dict[str, float] = {}
        for raw in selections:
            line_id = _text(raw.get("line_id"))
            quantity = float(raw.get("quantity") or 0)
            if not line_id or quantity <= 0:
                raise ValueError("Every selected supplier line requires a positive quantity.")
            if line_id in selected_quantities:
                raise ValueError("Each supplier offer line may be selected only once.")
            selected_quantities[line_id] = quantity

        with self._sessions() as session:
            offer = session.get(SupplierOffer, offer_id)
            if not offer or offer.organization_id != organization_id or offer.facility_id != facility_id:
                raise ValueError("Supplier offer was not found in the active facility.")
            if offer.status != "accepted":
                raise ValueError("Accept the supplier offer review before creating a purchase-order proposal.")
            freshness = self._freshness(offer, max(1, min(int(stale_after_days), 90)))
            if freshness["state"] in {"expired", "not_yet_effective"}:
                raise ValueError("The supplier offer is not currently effective and cannot create a purchase-order proposal.")
            partner = session.get(TradePartner, offer.partner_id)
            if not partner or partner.organization_id != organization_id or partner.partner_type not in {"vendor", "both"}:
                raise ValueError("The supplier vendor is no longer available for purchasing.")
            lines = list(
                session.scalars(
                    select(SupplierOfferLine).where(
                        SupplierOfferLine.offer_id == offer.id,
                        SupplierOfferLine.id.in_(selected_quantities),
                    )
                )
            )
            by_id = {line.id: line for line in lines}
            if set(by_id) != set(selected_quantities):
                raise ValueError("One or more selected supplier lines do not belong to this offer revision.")

            po_lines: list[dict[str, Any]] = []
            preview_lines: list[dict[str, Any]] = []
            total = 0.0
            for line_id in sorted(selected_quantities):
                line = by_id[line_id]
                quantity = selected_quantities[line_id]
                if not line.product_id:
                    raise ValueError(f"Map {line.product_name} to a canonical DoobieLogic product before creating a PO proposal.")
                product = session.get(Product, line.product_id)
                if not product or product.organization_id != organization_id or not product.active:
                    raise ValueError(f"The canonical product mapping for {line.product_name} is unavailable.")
                if quantity > float(line.available_quantity) + 1e-9:
                    raise ValueError(f"Selected quantity exceeds supplier availability for {line.product_name}.")
                minimum = float(line.minimum_order_quantity or 0)
                if minimum > 0 and quantity + 1e-9 < minimum:
                    raise ValueError(f"Selected quantity is below the supplier minimum for {line.product_name}.")
                availability_unit = _norm(line.availability_unit)
                price_basis = _norm(line.price_basis)
                if availability_unit != price_basis:
                    raise ValueError(
                        f"Automatic PO conversion for {line.product_name} requires price basis and availability unit to match."
                    )
                lineage = {
                    "source": "supplier_portal",
                    "partner_id": offer.partner_id,
                    "supplier_offer_id": offer.id,
                    "offer_group_id": offer.offer_group_id,
                    "offer_revision": offer.revision,
                    "supplier_offer_line_id": line.id,
                    "supplier_external_reference": offer.external_reference,
                    "supplier_sku": line.supplier_sku,
                    "batch_lot_identifier": line.batch_lot_identifier,
                    "coa_reference": line.coa_reference,
                    "quoted_unit_price": line.unit_price,
                    "quoted_price_basis": line.price_basis,
                }
                line_total = quantity * float(line.unit_price)
                total += line_total
                po_lines.append(
                    {
                        "product_id": product.id,
                        "quantity": quantity,
                        "unit": line.availability_unit,
                        "unit_price": line.unit_price,
                        "description": product.name,
                        "notes": supplier_lineage_note(lineage),
                    }
                )
                preview_lines.append(
                    {
                        "line_id": line.id,
                        "product_id": product.id,
                        "product_name": product.name,
                        "quantity": quantity,
                        "unit": line.availability_unit,
                        "unit_price": line.unit_price,
                        "line_total": round(line_total, 2),
                        "coa_reference": line.coa_reference,
                        "batch_lot_identifier": line.batch_lot_identifier,
                    }
                )

        selection_key = json.dumps(
            [{"line_id": key, "quantity": selected_quantities[key]} for key in sorted(selected_quantities)],
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(f"{offer.id}|{selection_key}".encode("utf-8")).hexdigest()
        clean_order_number = _text(order_number).upper() or f"SUP-{date.today():%Y%m%d}-{offer.id[:6].upper()}-{digest[:6].upper()}"
        payload = {
            "partner_id": offer.partner_id,
            "order_number": clean_order_number,
            "order_date": date.today().isoformat(),
            "due_date": due_date.isoformat() if due_date else None,
            "external_reference": offer.external_reference or f"SUPPLIER-OFFER:{offer.id}",
            "notes": f"Approved supplier offer {offer.id} revision {offer.revision}. Source lineage is preserved on each PO line.",
            "lines": po_lines,
        }
        preview = {
            "supplier_offer_id": offer.id,
            "offer_group_id": offer.offer_group_id,
            "offer_revision": offer.revision,
            "partner_id": offer.partner_id,
            "supplier_name": partner.name,
            "freshness": freshness,
            "order_number": clean_order_number,
            "financial_impact_usd": round(total, 2),
            "lines": preview_lines,
            "warning": "This is a proposal only. No purchase order, inventory, receiving, or compliance state changes until human approval and deterministic execution.",
        }
        return DoobieActionService(self.engine).propose(
            organization_id=organization_id,
            facility_id=facility_id,
            action_type="create_purchase_order",
            title=f"Create PO from {partner.name} supplier offer",
            rationale=f"Buyer selected {len(po_lines)} reviewed supplier offer line(s) for deterministic purchase-order creation.",
            payload=payload,
            preview=preview,
            actor=actor,
            idempotency_key=f"supplier-po:{offer.id}:{digest}",
            financial_impact_usd=total,
            risk_level="medium",
            source_type="supplier_portal",
            source_id=offer.id,
        )
