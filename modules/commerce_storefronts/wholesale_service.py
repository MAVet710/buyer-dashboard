"""Wholesale inventory projection layered on the shared organization inventory truth."""

from __future__ import annotations

import json
from typing import Any

from modules.coman.models import InventoryLot, Product
from modules.commercial.repository import CommercialRepository
from modules.inventory_availability.service import InventoryAvailabilityService

from .service import CommerceStorefrontService

_PASSED_LAB_STATES = {"passed", "testpassed", "released", "pass"}
_BULK_UNITS = {"g", "gram", "grams", "kg", "kilogram", "kilograms", "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds"}
_BULK_TOKENS = (
    "bulk",
    "biomass",
    "trim",
    "fresh frozen",
    "material",
    "distillate",
    "crude",
    "resin",
    "rosin",
    "concentrate",
    "oil",
)


def _metadata(lot: InventoryLot) -> dict[str, Any]:
    try:
        value = json.loads(lot.notes or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _lab_state(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _inventory_type(product: Product) -> str:
    unit = str(product.base_unit or "").strip().casefold()
    descriptor = f"{product.item_type or ''} {product.name or ''}".casefold().replace("_", " ")
    if unit in _BULK_UNITS or any(token in descriptor for token in _BULK_TOKENS):
        return "bulk"
    return "retail_ready"


class WholesaleCommerceStorefrontService(CommerceStorefrontService):
    """Commerce service whose catalog is restricted to truly wholesale-sellable inventory."""

    def wholesale_inventory(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        availability = InventoryAvailabilityService(self.engine).facility_snapshot(organization_id, facility_id)
        eligible: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []

        for availability_row in availability["lots"]:
            lot = availability_row["lot"]
            product = availability_row["product"]
            if not product or not product.active:
                continue
            meta = _metadata(lot)
            lab_testing_state = str(meta.get("lab_testing_state") or "").strip()
            coa_reference = str(meta.get("coa_reference") or "").strip()
            on_hand = max(0.0, float(availability_row["on_hand"] or 0.0))
            reserved = max(0.0, float(availability_row["reserved"] or 0.0))
            usable = max(0.0, float(availability_row["available"] or 0.0))
            released = str(lot.status or "").casefold() in {"available", "released"}
            coa_passed = bool(coa_reference) and _lab_state(lab_testing_state) in _PASSED_LAB_STATES
            reasons: list[str] = []
            if not released:
                reasons.append("Inventory is not released")
            if not coa_reference:
                reasons.append("COA reference is missing")
            elif not coa_passed:
                reasons.append("COA is not in a passed/released state")
            if usable <= 0:
                reasons.append("No uncommitted quantity is available")
            row = {
                "lot_id": lot.id,
                "package_id": lot.compliance_package_id or lot.lot_code,
                "lot_code": lot.lot_code,
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "item_type": product.item_type,
                "inventory_type": _inventory_type(product),
                "available": on_hand,
                "reserved": reserved,
                "production_reserved": float(availability_row["production_reserved"]),
                "wholesale_reserved": float(availability_row["wholesale_reserved"]),
                "wholesale_committed": float(availability_row["wholesale_committed"]),
                "usable": usable,
                "claims": availability_row["claims"],
                "unit": product.base_unit,
                "location": lot.location_code,
                "status": lot.status,
                "lab_testing_state": lab_testing_state,
                "coa_reference": coa_reference,
                "received_at": lot.received_at,
                "expiration_at": lot.expiration_at,
                "unit_cost": float(product.unit_cost or 0.0),
                "suggested_price_usd": float(product.retail_price or 0.0),
                "eligible": released and coa_passed and usable > 0,
                "blocked_reasons": reasons,
            }
            (eligible if row["eligible"] else blocked).append(row)

        return {
            "items": eligible,
            "blocked_items": blocked,
            "summary": {
                "sellable_lots": len(eligible),
                "bulk_lots": sum(row["inventory_type"] == "bulk" for row in eligible),
                "retail_ready_lots": sum(row["inventory_type"] == "retail_ready" for row in eligible),
                "sellable_quantity": sum(float(row["usable"]) for row in eligible),
                "blocked_lots": len(blocked),
                "production_reserved_quantity": sum(float(row["production_reserved"]) for row in eligible + blocked),
                "wholesale_reserved_quantity": sum(float(row["wholesale_reserved"]) for row in eligible + blocked),
                "wholesale_committed_quantity": sum(float(row["wholesale_committed"]) for row in eligible + blocked),
            },
            "eligibility_policy": {
                "requires_released_inventory": True,
                "requires_passed_coa": True,
                "requires_positive_uncommitted_quantity": True,
                "respects_organization_wide_commitments": True,
            },
        }

    def list_catalog_options(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        inventory = self.wholesale_inventory(organization_id, facility_id)
        by_product: dict[str, dict[str, Any]] = {}
        for lot in inventory["items"]:
            row = by_product.setdefault(lot["product_id"], {
                "product_id": lot["product_id"],
                "sku": lot["sku"],
                "name": lot["name"],
                "unit": lot["unit"],
                "available": 0.0,
                "suggested_price_usd": lot["suggested_price_usd"],
                "inventory_type": lot["inventory_type"],
                "coa_passed": True,
            })
            row["available"] += float(lot["usable"])
        return sorted(by_product.values(), key=lambda row: (row["name"].casefold(), row["sku"].casefold()))

    def merchandising_catalog_options(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        """Return every stocked product so held items can be merchandised before release.

        Public catalog eligibility remains strict and continues to use
        ``list_catalog_options``. This projection is only for the authenticated
        storefront manager and makes each blocker explicit.
        """
        inventory = self.wholesale_inventory(organization_id, facility_id)
        by_product: dict[str, dict[str, Any]] = {}
        for lot in inventory["items"] + inventory["blocked_items"]:
            row = by_product.setdefault(lot["product_id"], {
                "product_id": lot["product_id"],
                "sku": lot["sku"],
                "name": lot["name"],
                "unit": lot["unit"],
                "available": 0.0,
                "on_hand": 0.0,
                "suggested_price_usd": lot["suggested_price_usd"],
                "inventory_type": lot["inventory_type"],
                "eligible": False,
                "blocked_reasons": set(),
            })
            row["on_hand"] += float(lot["available"])
            row["available"] += float(lot["usable"]) if lot["eligible"] else 0.0
            row["eligible"] = bool(row["eligible"] or lot["eligible"])
            row["blocked_reasons"].update(lot["blocked_reasons"])
        result = []
        for row in by_product.values():
            row["blocked_reasons"] = [] if row["eligible"] else sorted(row["blocked_reasons"])
            result.append(row)
        return sorted(result, key=lambda row: (row["name"].casefold(), row["sku"].casefold()))

    def approve_order_request(self, *, organization_id: str, facility_id: str, request_id: str, actor: str, review_note: str = "") -> dict[str, Any]:
        result = super().approve_order_request(
            organization_id=organization_id,
            facility_id=facility_id,
            request_id=request_id,
            actor=actor,
            review_note=review_note,
        )
        order = CommercialRepository(self.engine).confirm_order(
            result["order_id"],
            organization_id=organization_id,
            facility_id=facility_id,
            actor=actor,
        )
        result["order_status"] = order.status
        return result
