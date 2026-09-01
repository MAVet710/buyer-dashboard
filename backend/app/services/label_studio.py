"""Authoritative inventory-to-label projection for Label Studio.

The projection is intentionally read-only. It derives label candidates from the
active organization/facility inventory scope and only fills values that already
exist in durable product, facility, lot, or QA evidence. It never guesses legal
label content from a product name or from the total lot balance.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Product
from modules.inventory_quality.models import LotQualityEvidence
from modules.product_master.models import ProductMasterProfile


_LABEL_ORDER = (
    "product_name",
    "brand",
    "strain",
    "product_type",
    "net_contents",
    "license_number",
    "facility_name",
    "package_id",
    "batch_number",
    "potency",
    "lab_testing_state",
    "laboratory",
    "test_date",
    "coa_reference",
    "ingredients",
    "allergens",
    "manufacture_date",
    "package_date",
    "expiration_date",
    "warning_text",
)


def _metadata(lot: InventoryLot) -> dict[str, Any]:
    raw = str(lot.notes or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).strip()


def _date_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return _text(value)


def _percent(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return ""
    return f"{number:g}%"


def _first(meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(meta.get(key))
        if value:
            return value
    return ""


def _profile_or_meta(profile_value: Any, meta: dict[str, Any], *keys: str) -> str:
    return _text(profile_value) or _first(meta, *keys)


def _net_contents(meta: dict[str, Any]) -> str:
    direct = _first(meta, "net_contents", "package_size", "declared_net_contents")
    if direct:
        return direct
    for value_key, unit_key in (
        ("net_weight", "net_weight_unit"),
        ("unit_weight", "unit_weight_unit"),
        ("package_weight", "package_weight_unit"),
    ):
        value = _text(meta.get(value_key))
        unit = _text(meta.get(unit_key))
        if value:
            return f"{value} {unit}".strip()
    return ""


def _potency(meta: dict[str, Any], quality: LotQualityEvidence | None) -> str:
    entries: list[str] = []
    thca = quality.thca_percent if quality and quality.thca_percent is not None else meta.get("thca_percent")
    total_thc = meta.get("total_thc_percent")
    tac = quality.tac_percent if quality and quality.tac_percent is not None else meta.get("tac_percent")
    terpenes = quality.total_terpenes_percent if quality and quality.total_terpenes_percent is not None else meta.get("total_terpenes_percent")
    for label, value in (("THCA", thca), ("Total THC", total_thc), ("TAC", tac), ("Total terpenes", terpenes)):
        formatted = _percent(value)
        if formatted:
            entries.append(f"{label} {formatted}")
    return " · ".join(entries)


def _raw_text(label: dict[str, str]) -> str:
    return "\n".join(label[key] for key in _LABEL_ORDER if label.get(key))


class LabelInventoryService:
    """Read inventory label candidates within one tenant/facility boundary."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def list_sources(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        balance = (
            select(
                InventoryTransaction.lot_id.label("lot_id"),
                func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
            )
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
            )
            .group_by(InventoryTransaction.lot_id)
            .subquery()
        )
        stmt = (
            select(
                InventoryLot,
                Product,
                Facility,
                ProductMasterProfile,
                LotQualityEvidence,
                func.coalesce(balance.c.balance, 0.0),
            )
            .join(Product, Product.id == InventoryLot.product_id)
            .join(Facility, Facility.id == InventoryLot.facility_id)
            .outerjoin(
                ProductMasterProfile,
                (ProductMasterProfile.product_id == Product.id)
                & (ProductMasterProfile.organization_id == organization_id),
            )
            .outerjoin(LotQualityEvidence, LotQualityEvidence.lot_id == InventoryLot.id)
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                Product.organization_id == organization_id,
                Facility.organization_id == organization_id,
                func.coalesce(balance.c.balance, 0.0) > 0,
            )
            .order_by(Product.name.asc(), InventoryLot.received_at.desc().nullslast(), InventoryLot.lot_code.asc())
        )
        with Session(self.engine) as session:
            rows = session.execute(stmt).all()
        return [self._source(*row) for row in rows]

    def get_source(self, organization_id: str, facility_id: str, lot_id: str) -> dict[str, Any]:
        row = next((item for item in self.list_sources(organization_id, facility_id) if item["lot_id"] == lot_id), None)
        if row is None:
            raise ValueError("Inventory batch was not found in the active facility or has no on-hand balance.")
        return row

    @staticmethod
    def _source(
        lot: InventoryLot,
        product: Product,
        facility: Facility,
        profile: ProductMasterProfile | None,
        quality: LotQualityEvidence | None,
        balance: float,
    ) -> dict[str, Any]:
        meta = _metadata(lot)
        lab_state = _text(quality.lab_testing_state if quality else "") or _first(meta, "lab_testing_state")
        coa_reference = _text(quality.coa_reference if quality else "") or _first(meta, "coa_reference")
        coa_url = _text(quality.coa_url if quality else "") or _first(meta, "coa_url", "certificate_url", "lab_report_url")
        package_id = _text(lot.compliance_package_id) or _first(meta, "source_tracking_number", "package_id", "metrc_package_id", "traceability_package_id")
        profile_category = (profile.category or profile.product_format) if profile else ""
        label = {
            "product_name": _text(product.name),
            "brand": _profile_or_meta(profile.brand if profile else "", meta, "brand"),
            "strain": _profile_or_meta(profile.strain if profile else "", meta, "strain"),
            "product_type": (_text(profile_category) or _first(meta, "category", "product_type") or product.item_type.replace("_", " ")).title(),
            "net_contents": _net_contents(meta),
            "license_number": _text(facility.license_number),
            "facility_name": _text(facility.name),
            "manufacturer": _profile_or_meta(profile.manufacturer if profile else "", meta, "manufacturer"),
            "package_id": package_id,
            "batch_number": _first(meta, "batch_number", "batch_name", "source_lot_code") or _text(lot.lot_code),
            "sku": _text(product.sku),
            "upc": _text(product.upc),
            "potency": _potency(meta, quality),
            "lab_testing_state": lab_state,
            "laboratory": _first(meta, "laboratory", "lab_name", "testing_laboratory"),
            "test_date": _date_text(meta.get("analysis_date") or meta.get("test_date") or (quality.verified_at if quality else None)),
            "coa_reference": coa_reference,
            "coa_url": coa_url,
            "ingredients": _first(meta, "ingredients", "ingredient_statement"),
            "allergens": _first(meta, "allergens", "allergen_statement"),
            "harvest_date": _date_text(meta.get("harvest_date") or meta.get("harvested_at")),
            "manufacture_date": _date_text(meta.get("manufacture_date") or meta.get("manufactured_at")),
            "package_date": _date_text(meta.get("package_date") or meta.get("packaged_at")),
            "expiration_date": _date_text(lot.expiration_at or meta.get("expiration_date") or meta.get("best_by")),
            "warning_text": _first(meta, "warning_text", "warnings", "required_warning"),
            "universal_symbol": _first(meta, "universal_symbol", "universal_symbol_text"),
            "qr_value": coa_url or coa_reference or package_id,
        }
        return {
            "lot_id": lot.id,
            "product_id": product.id,
            "package_id": package_id,
            "lot_code": lot.lot_code,
            "product_name": product.name,
            "sku": product.sku,
            "location": lot.location_code,
            "status": lot.status,
            "on_hand": float(balance or 0.0),
            "inventory_unit": product.base_unit,
            "label": label,
            "raw_text": _raw_text(label),
            "source_summary": {
                "facility": facility.name,
                "license_number": facility.license_number,
                "license_type": facility.license_type,
                "qa_source": quality.evidence_source if quality else _text(meta.get("quality_evidence_source") or "inventory metadata"),
            },
        }
