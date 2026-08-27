"""Wholesale inventory projection layered on the existing durable production inventory ledger."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, MaterialReservation, Product
from modules.coman.repository import ComanRepository

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
        repo = ComanRepository(self.engine)
        with Session(self.engine) as session:
            lots = list(session.scalars(select(InventoryLot).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            ).order_by(InventoryLot.received_at.desc().nullslast())))
            product_ids = {lot.product_id for lot in lots}
            products = {
                row.id: row
                for row in session.scalars(select(Product).where(
                    Product.organization_id == organization_id,
                    Product.id.in_(product_ids),
                    Product.active.is_(True),
                ))
            } if product_ids else {}
            reserved_rows = session.execute(
                select(
                    MaterialReservation.lot_id,
                    func.coalesce(func.sum(MaterialReservation.quantity), 0.0),
                ).where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                    MaterialReservation.status == "reserved",
                ).group_by(MaterialReservation.lot_id)
            ).all()
        reserved_by_lot = {lot_id: float(quantity or 0.0) for lot_id, quantity in reserved_rows}

        eligible: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for lot in lots:
            product = products.get(lot.product_id)
            if not product:
                continue
            meta = _metadata(lot)
            lab_testing_state = str(meta.get("lab_testing_state") or "").strip()
            coa_reference = str(meta.get("coa_reference") or "").strip()
            balance = max(0.0, float(repo.inventory_balance(organization_id, lot.id) or 0.0))
            reserved = max(0.0, reserved_by_lot.get(lot.id, 0.0))
            usable = max(0.0, balance - reserved)
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
                "available": balance,
                "reserved": reserved,
                "usable": usable,
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
            },
            "eligibility_policy": {
                "requires_released_inventory": True,
                "requires_passed_coa": True,
                "requires_positive_uncommitted_quantity": True,
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
