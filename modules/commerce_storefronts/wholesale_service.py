"""Wholesale inventory projection layered on the shared organization inventory truth."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrderLine, InventoryLot, Product
from modules.commercial.repository import CommercialRepository
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.product_master.models import ProductMasterProfile

from .sales_units import StorefrontProductSalesUnit, compatible_sales_units, conversion_factor, convert_quantity, convert_unit_price, normalize_unit
from .service import CommerceStorefrontService

_PASSED_LAB_STATES = {"passed", "testpassed", "released", "pass"}
_BULK_UNITS = {"g", "gram", "grams", "kg", "kilogram", "kilograms", "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds"}
_BULK_TOKENS = ("bulk", "biomass", "trim", "fresh frozen", "material", "distillate", "crude", "resin", "rosin", "concentrate", "oil")
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
    value_keys = {_normalized_key(candidate) for candidate in _LAB_VALUE_KEYS}
    for container in _lab_containers(meta):
        for raw_key, raw_value in container.items():
            if _normalized_key(raw_key) in alias_keys:
                parsed = _percent_number(raw_value)
                if parsed is not None:
                    return parsed
        test_name = next((value for key, value in container.items() if _normalized_key(key) in {"testtypename", "testname", "analyte", "name"}), None)
        if _normalized_key(test_name) in alias_keys:
            for key, value in container.items():
                if _normalized_key(key) in value_keys:
                    parsed = _percent_number(value)
                    if parsed is not None:
                        return parsed
    return None


def _lab_range(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"minimum": None, "maximum": None}
    return {"minimum": round(min(values), 2), "maximum": round(max(values), 2)}


def _empty_lab_stats() -> dict[str, dict[str, float | None]]:
    return {"thca": _lab_range([]), "tac": _lab_range([]), "terpenes": _lab_range([])}


def _first_text(meta: dict[str, Any], *keys: str) -> str:
    normalized = {_normalized_key(key) for key in keys}
    for container in [meta, *[value for value in meta.values() if isinstance(value, dict)]]:
        for raw_key, value in container.items():
            if _normalized_key(raw_key) in normalized and value not in (None, ""):
                return str(value).strip()
    return ""


def _https_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.casefold().startswith("https://") else ""


def _profile_dict(profile: ProductMasterProfile | None) -> dict[str, Any]:
    if not profile:
        return {"brand": "", "category": "", "subcategory": "", "strain": "", "product_format": "", "image_url": "", "description": ""}
    return {
        "brand": profile.brand,
        "category": profile.category,
        "subcategory": profile.subcategory,
        "strain": profile.strain,
        "product_format": profile.product_format,
        "image_url": profile.image_url,
        "description": profile.description,
    }


class WholesaleCommerceStorefrontService(CommerceStorefrontService):
    """Commerce service whose catalog is restricted to truly wholesale-sellable inventory."""

    def _sales_units(self, storefront_id: str) -> dict[str, str]:
        if not storefront_id:
            return {}
        with Session(self.engine) as session:
            return {
                row.product_id: normalize_unit(row.sales_unit)
                for row in session.scalars(
                    select(StorefrontProductSalesUnit).where(StorefrontProductSalesUnit.storefront_id == storefront_id)
                )
            }

    def _listing_sales_unit(self, storefront_id: str, product: Product | None) -> str:
        if not product:
            return ""
        return self._sales_units(storefront_id).get(product.id) or normalize_unit(product.base_unit)

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
            coa_url = _https_url(meta.get("coa_url") or meta.get("certificate_url") or meta.get("lab_report_url") or coa_reference)
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
                "batch_name": _first_text(meta, "batch_name", "production_batch", "harvest_name", "batch") or lot.lot_code,
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
                "coa_url": coa_url,
                "thca_percent": _lab_percent(meta, "thca", "thca_percent", "thca_pct", "thc acid", "tetrahydrocannabinolic acid"),
                "tac_percent": _lab_percent(meta, "tac", "tac_percent", "total active cannabinoids", "total_active_cannabinoids", "total_active_cannabinoids_percent"),
                "terpenes_percent": _lab_percent(meta, "terpenes", "terps", "terpenes_percent", "total terpenes", "total_terpenes", "total_terpenes_percent"),
                "harvested_at": _first_text(meta, "harvested_at", "harvest_date", "harvested_date"),
                "produced_at": _first_text(meta, "produced_at", "production_date", "packaged_date", "package_date"),
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
            "eligibility_policy": {"requires_released_inventory": True, "requires_passed_coa": True, "requires_positive_uncommitted_quantity": True, "respects_organization_wide_commitments": True, "lab_stats_use_passed_real_batches_only": True},
        }

    def _profiles(self, organization_id: str) -> dict[str, ProductMasterProfile]:
        with Session(self.engine) as session:
            return {row.product_id: row for row in session.scalars(select(ProductMasterProfile).where(ProductMasterProfile.organization_id == organization_id))}

    def list_catalog_options(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        inventory = self.wholesale_inventory(organization_id, facility_id)
        profiles = self._profiles(organization_id)
        storefront = self.get_storefront(organization_id, facility_id)
        sales_units = self._sales_units(storefront.id) if storefront else {}
        by_product: dict[str, dict[str, Any]] = {}
        for lot in inventory["items"]:
            row = by_product.setdefault(lot["product_id"], {
                "product_id": lot["product_id"], "sku": lot["sku"], "name": lot["name"], "unit": lot["unit"], "available": 0.0,
                "suggested_price_usd": lot["suggested_price_usd"], "inventory_type": lot["inventory_type"], "coa_passed": True,
                "test_quantity": 0.0, "_lab_values": {"thca": [], "tac": [], "terpenes": []}, "batches": [],
                **_profile_dict(profiles.get(lot["product_id"])),
            })
            row["available"] += float(lot["usable"])
            if lot["test_data"]:
                row["test_quantity"] += float(lot["usable"])
                continue
            for metric, source_key in (("thca", "thca_percent"), ("tac", "tac_percent"), ("terpenes", "terpenes_percent")):
                value = lot[source_key]
                if value is not None:
                    row["_lab_values"][metric].append(float(value))
            row["batches"].append({
                "lot_id": lot["lot_id"], "lot_code": lot["lot_code"], "package_id": lot["package_id"], "batch_name": lot["batch_name"],
                "available": float(lot["usable"]), "unit": lot["unit"], "coa_reference": lot["coa_reference"], "coa_url": lot["coa_url"],
                "thca_percent": lot["thca_percent"], "tac_percent": lot["tac_percent"], "terpenes_percent": lot["terpenes_percent"],
                "harvested_at": lot["harvested_at"], "produced_at": lot["produced_at"], "received_at": lot["received_at"], "expiration_at": lot["expiration_at"],
            })
        for row in by_product.values():
            real_quantity = row["available"] - row["test_quantity"]
            row["orderable"] = real_quantity > 0
            row["test_preview"] = not row["orderable"] and row["test_quantity"] > 0
            if row["orderable"]:
                row["available"] = real_quantity
            values = row.pop("_lab_values")
            row["lab_stats"] = {metric: _lab_range(metric_values) for metric, metric_values in values.items()}
            row["batches"].sort(key=lambda batch: str(batch.get("received_at") or ""), reverse=True)
            row["primary_batch"] = row["batches"][0] if row["batches"] else None
            base_unit = normalize_unit(row["unit"])
            sales_unit = sales_units.get(row["product_id"]) or base_unit
            row["base_unit"] = base_unit
            row["sales_unit"] = sales_unit
            row["compatible_sales_units"] = compatible_sales_units(base_unit)
            if sales_unit != base_unit:
                row["available"] = convert_quantity(row["available"], base_unit, sales_unit)
                row["test_quantity"] = convert_quantity(row["test_quantity"], base_unit, sales_unit)
                for batch in row["batches"]:
                    batch["available"] = convert_quantity(batch["available"], base_unit, sales_unit)
                    batch["unit"] = sales_unit
            row["unit"] = sales_unit
        return sorted(by_product.values(), key=lambda row: (row["name"].casefold(), row["sku"].casefold()))

    def admin_snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        result = super().admin_snapshot(organization_id, facility_id)
        storefront = self.get_storefront(organization_id, facility_id)
        if not storefront:
            return result
        sales_units = self._sales_units(storefront.id)
        with Session(self.engine) as session:
            products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == organization_id))}
        for item in result.get("products", []):
            product = products.get(item.get("product_id"))
            if not product:
                continue
            base_unit = normalize_unit(product.base_unit)
            sales_unit = sales_units.get(product.id) or base_unit
            item["base_unit"] = base_unit
            item["sales_unit"] = sales_unit
            item["unit"] = sales_unit
            item["compatible_sales_units"] = compatible_sales_units(base_unit)
        return result

    def public_catalog(self, slug: str) -> dict[str, Any]:
        storefront = self.resolve_public(slug)
        sales_units = self._sales_units(storefront.id)
        sellable = {row["product_id"]: row for row in self.list_catalog_options(storefront.organization_id, storefront.facility_id)}
        merch = {row["product_id"]: row for row in self.merchandising_catalog_options(storefront.organization_id, storefront.facility_id)}
        result = super().public_catalog(slug)
        profiles = self._profiles(storefront.organization_id)
        safe_catalog: list[dict[str, Any]] = []
        for item in result["catalog"]:
            base_unit = normalize_unit(item.get("unit") or "")
            sales_unit = sales_units.get(item["product_id"]) or base_unit
            option = sellable.get(item["product_id"])
            merch_row = merch.get(item["product_id"], {})
            blocked_reasons = set(merch_row.get("blocked_reasons") or [])
            if "COA is not in a passed/released state" in blocked_reasons:
                continue
            profile = _profile_dict(profiles.get(item["product_id"]))
            if option:
                item.update({key: option.get(key) for key in ("lab_stats", "batches", "primary_batch", "inventory_type", "base_unit", "sales_unit", "compatible_sales_units")})
                for key in ("brand", "category", "subcategory", "strain", "product_format", "image_url", "description"):
                    item[key] = option.get(key) or profile.get(key, "")
            else:
                item["lab_stats"] = _empty_lab_stats()
                item["batches"] = []
                item["primary_batch"] = None
                item.update(profile)
                item["base_unit"] = base_unit
                item["sales_unit"] = sales_unit
                item["compatible_sales_units"] = compatible_sales_units(base_unit)
            if base_unit and sales_unit and sales_unit != base_unit:
                item["minimum_quantity"] = convert_quantity(float(item.get("minimum_quantity") or 0.0), base_unit, sales_unit)
                item["case_quantity"] = convert_quantity(float(item.get("case_quantity") or 0.0), base_unit, sales_unit)
                item["price_usd"] = convert_unit_price(float(item.get("price_usd") or 0.0), base_unit, sales_unit)
                projected_breaks: list[dict[str, Any]] = []
                for raw_tier in item.get("quantity_breaks") or []:
                    tier = dict(raw_tier)
                    if tier.get("minimum_quantity") is not None:
                        tier["minimum_quantity"] = convert_quantity(float(tier["minimum_quantity"]), base_unit, sales_unit)
                    if tier.get("price_usd") is not None:
                        tier["price_usd"] = convert_unit_price(float(tier["price_usd"]), base_unit, sales_unit)
                    projected_breaks.append(tier)
                item["quantity_breaks"] = projected_breaks
            item["unit"] = sales_unit
            if item.get("orderable"):
                item["availability_status"] = "in_stock"
            elif option and option.get("test_preview"):
                item["availability_status"] = "preview"
            elif float(merch_row.get("on_hand") or 0) > 0:
                item["availability_status"] = "coming_soon"
            else:
                item["availability_status"] = "sold_out"
            safe_catalog.append(item)
        result["catalog"] = safe_catalog
        return result

    def merchandising_catalog_options(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        inventory = self.wholesale_inventory(organization_id, facility_id)
        profiles = self._profiles(organization_id)
        storefront = self.get_storefront(organization_id, facility_id)
        sales_units = self._sales_units(storefront.id) if storefront else {}
        by_product: dict[str, dict[str, Any]] = {}
        for lot in inventory["items"] + inventory["blocked_items"]:
            row = by_product.setdefault(lot["product_id"], {
                "product_id": lot["product_id"], "sku": lot["sku"], "name": lot["name"], "unit": lot["unit"], "available": 0.0, "on_hand": 0.0,
                "suggested_price_usd": lot["suggested_price_usd"], "inventory_type": lot["inventory_type"], "eligible": False, "blocked_reasons": set(),
                **_profile_dict(profiles.get(lot["product_id"])),
            })
            row["on_hand"] += float(lot["available"])
            row["available"] += float(lot["usable"]) if lot["eligible"] and not lot["test_data"] else 0.0
            row["eligible"] = bool(row["eligible"] or (lot["eligible"] and not lot["test_data"]))
            row["blocked_reasons"].update(lot["blocked_reasons"])
        result = []
        for row in by_product.values():
            row["blocked_reasons"] = [] if row["eligible"] else sorted(row["blocked_reasons"])
            base_unit = normalize_unit(row["unit"])
            sales_unit = sales_units.get(row["product_id"]) or base_unit
            row["base_unit"] = base_unit
            row["sales_unit"] = sales_unit
            row["compatible_sales_units"] = compatible_sales_units(base_unit)
            if sales_unit != base_unit:
                row["available"] = convert_quantity(row["available"], base_unit, sales_unit)
                row["on_hand"] = convert_quantity(row["on_hand"], base_unit, sales_unit)
            row["unit"] = sales_unit
            result.append(row)
        return sorted(result, key=lambda row: (row["name"].casefold(), row["sku"].casefold()))

    def submit_order_request(self, **kwargs: Any):
        slug = str(kwargs.get("slug") or "")
        catalog = self.public_catalog(slug)
        by_product = {row["product_id"]: row for row in catalog["catalog"]}
        for requested in kwargs.get("lines") or []:
            item = by_product.get(str(requested.get("product_id") or ""))
            if item and item.get("availability_status") == "preview" and not item.get("orderable"):
                raise ValueError(f"{item['name']} is test-preview inventory and cannot be ordered.")
        return super().submit_order_request(**kwargs)

    def _normalize_commercial_order_to_base_units(self, order_id: str, organization_id: str) -> None:
        with Session(self.engine) as session, session.begin():
            lines = list(session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == order_id, CommercialOrderLine.organization_id == organization_id)))
            for line in lines:
                product = session.get(Product, line.product_id)
                if not product:
                    continue
                base_unit = normalize_unit(product.base_unit)
                sales_unit = normalize_unit(line.unit)
                if not base_unit or not sales_unit or base_unit == sales_unit:
                    continue
                factor = conversion_factor(sales_unit, base_unit)
                line.quantity = float(line.quantity) * factor
                line.fulfilled_quantity = float(line.fulfilled_quantity or 0.0) * factor
                line.unit_price = convert_unit_price(float(line.unit_price), sales_unit, base_unit)
                original_note = str(line.notes or "").strip()
                unit_note = f"Storefront sales unit: {sales_unit}; operational inventory unit: {base_unit}."
                line.notes = " ".join(value for value in (original_note, unit_note) if value)
                line.unit = base_unit
            session.flush()

    def approve_order_request(self, *, organization_id: str, facility_id: str, request_id: str, actor: str, review_note: str = "", approved_lines: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        result = super().approve_order_request(organization_id=organization_id, facility_id=facility_id, request_id=request_id, actor=actor, review_note=review_note, approved_lines=approved_lines)
        self._normalize_commercial_order_to_base_units(result["order_id"], organization_id)
        order = CommercialRepository(self.engine).confirm_order(result["order_id"], organization_id=organization_id, facility_id=facility_id, actor=actor)
        result["order_status"] = order.status
        return result
