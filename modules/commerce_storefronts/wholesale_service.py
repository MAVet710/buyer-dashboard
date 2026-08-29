"""Wholesale inventory projection layered on the shared organization inventory truth."""

from __future__ import annotations

import json
import re
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
_LAB_CONTAINER_KEYS = ("coa", "lab", "lab_results", "potency", "cannabinoids", "results")
_LAB_VALUE_KEYS = ("value", "result", "test_result", "testresult", "percent", "percentage")


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


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _percent_number(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in _LAB_VALUE_KEYS:
            for raw_key, raw_value in value.items():
                if _normalized_key(raw_key) == _normalized_key(key):
                    return _percent_number(raw_value)
        return None
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip().replace("%", "").replace(",", "")
    if not raw:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 100:
        return None
    return round(number, 4)


def _lab_containers(meta: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = [meta]
    for key in _LAB_CONTAINER_KEYS:
        nested = meta.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
        elif isinstance(nested, list):
            containers.extend(row for row in nested if isinstance(row, dict))
    return containers


def _lab_percent(meta: dict[str, Any], *aliases: str) -> float | None:
    alias_keys = {_normalized_key(alias) for alias in aliases}
    for container in _lab_containers(meta):
        for raw_key, raw_value in container.items():
            if _normalized_key(raw_key) in alias_keys:
                parsed = _percent_number(raw_value)
                if parsed is not None:
                    return parsed

        test_name = next(
            (
                value
                for key, value in container.items()
                if _normalized_key(key) in {"testtypename", "testname", "analyte", "name"}
            ),
            None,
        )
        if _normalized_key(test_name) in alias_keys:
            for key, value in container.items():
                if _normalized_key(key) in {_normalized_key(candidate) for candidate in _LAB_VALUE_KEYS}:
                    parsed = _percent_number(value)
                    if parsed is not None:
                        return parsed
    return None


def _lab_range(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"minimum": None, "maximum": None}
    return {"minimum": round(min(values), 2), "maximum": round(max(values), 2)}


def _empty_lab_stats() -> dict[str, dict[str, float | None]]:
    return {
        "thca": _lab_range([]),
        "tac": _lab_range([]),
        "terpenes": _lab_range([]),
    }


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
                "thca_percent": _lab_percent(meta, "thca", "thca_percent", "thca_pct", "thc acid", "tetrahydrocannabinolic acid"),
                "tac_percent": _lab_percent(meta, "tac", "tac_percent", "total active cannabinoids", "total_active_cannabinoids", "total_active_cannabinoids_percent"),
                "terpenes_percent": _lab_percent(meta, "terpenes", "terps", "terpenes_percent", "total terpenes", "total_terpenes", "total_terpenes_percent"),
                "test_data": bool(meta.get("test_data", False)),
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
                "lab_stats_use_passed_real_batches_only": True,
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
                "test_quantity": 0.0,
                "_lab_values": {"thca": [], "tac": [], "terpenes": []},
            })
            row["available"] += float(lot["usable"])
            if lot["test_data"]:
                row["test_quantity"] += float(lot["usable"])
            else:
                for metric, source_key in (("thca", "thca_percent"), ("tac", "tac_percent"), ("terpenes", "terpenes_percent")):
                    value = lot[source_key]
                    if value is not None:
                        row["_lab_values"][metric].append(float(value))
        for row in by_product.values():
            real_quantity = row["available"] - row["test_quantity"]
            row["orderable"] = real_quantity > 0
            if row["orderable"]:
                row["available"] = real_quantity
            values = row.pop("_lab_values")
            row["lab_stats"] = {metric: _lab_range(metric_values) for metric, metric_values in values.items()}
        return sorted(by_product.values(), key=lambda row: (row["name"].casefold(), row["sku"].casefold()))

    def public_catalog(self, slug: str) -> dict[str, Any]:
        storefront = self.resolve_public(slug)
        lab_by_product = {
            row["product_id"]: row.get("lab_stats", _empty_lab_stats())
            for row in self.list_catalog_options(storefront.organization_id, storefront.facility_id)
        }
        result = super().public_catalog(slug)
        for item in result["catalog"]:
            item["lab_stats"] = lab_by_product.get(item["product_id"], _empty_lab_stats())
        return result

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
