"""Authoritative inventory-to-label projection for Label Studio.

The projection is intentionally read-only. It derives label candidates from the
active organization/facility inventory scope and only fills values that already
exist in durable product, facility, lot, packaging, or QA/COA evidence. The
METRC package/tag is the COA lookup key and the sole QR payload for a generated
label. It never guesses legal label content from a product name or from the total
lot balance.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import json
import re
from typing import Any

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import Facility, InventoryLot, InventoryTransaction, Product
from modules.inventory_quality.coa import CoaDocumentService
from modules.inventory_quality.models import CoaAnalyteResult, CoaDocument, LotQualityEvidence
from modules.product_master.models import ProductMasterProfile
from modules.product_master.packaging import ProductPackagingProfile


_LABEL_ORDER = (
    "product_name",
    "brand",
    "strain",
    "product_type",
    "package_size",
    "net_contents",
    "license_number",
    "facility_name",
    "package_id",
    "batch_number",
    "potency",
    "total_thc",
    "total_cbd",
    "total_cannabinoids",
    "total_terpenes",
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

_GRAMS_PER_OUNCE = Decimal("28.349523125")
_OUNCE_QUANTUM = Decimal("0.00001")
_WEIGHT_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(g|gram|grams|oz|ounce|ounces)\s*$", re.IGNORECASE)


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


def _quantity(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:g}"


def _first(meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(meta.get(key))
        if value:
            return value
    return ""


def _profile_or_meta(profile_value: Any, meta: dict[str, Any], *keys: str) -> str:
    return _text(profile_value) or _first(meta, *keys)


def _parse_weight(value: Any, unit: Any = "") -> tuple[Decimal, str] | None:
    value_text = _text(value)
    unit_text = _text(unit).casefold()
    if value_text and unit_text:
        try:
            return Decimal(value_text), unit_text
        except InvalidOperation:
            return None
    if not value_text:
        return None
    match = _WEIGHT_RE.match(value_text)
    if not match:
        return None
    try:
        return Decimal(match.group(1)), match.group(2).casefold()
    except InvalidOperation:
        return None


def _declared_weight(meta: dict[str, Any], packaging: ProductPackagingProfile | None) -> tuple[Decimal, str] | None:
    # Lot-level declarations remain the override for special/multipack packages.
    for key in ("net_contents", "package_size", "declared_net_contents"):
        parsed = _parse_weight(meta.get(key))
        if parsed:
            return parsed
    for value_key, unit_key in (
        ("net_weight", "net_weight_unit"),
        ("unit_weight", "unit_weight_unit"),
        ("package_weight", "package_weight_unit"),
    ):
        parsed = _parse_weight(meta.get(value_key), meta.get(unit_key))
        if parsed:
            return parsed
    if packaging and packaging.net_content > 0 and _text(packaging.net_content_unit):
        return Decimal(str(packaging.net_content)), _text(packaging.net_content_unit).casefold()
    return None


def _package_size(meta: dict[str, Any], packaging: ProductPackagingProfile | None) -> str:
    direct = _first(meta, "package_size", "declared_net_contents", "net_contents")
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
    if packaging and packaging.net_content > 0 and _text(packaging.net_content_unit):
        return f"{_quantity(packaging.net_content)} {_text(packaging.net_content_unit)}"
    return ""


def _format_ounces(value: Decimal) -> str:
    quantized = value.quantize(_OUNCE_QUANTUM, rounding=ROUND_DOWN)
    text = f"{quantized:.5f}"
    if text.startswith("0."):
        text = text[1:]
    return text


def _net_contents(meta: dict[str, Any], packaging: ProductPackagingProfile | None) -> str:
    declared = _declared_weight(meta, packaging)
    if declared is None:
        return _package_size(meta, packaging)
    value, unit = declared
    if unit in {"g", "gram", "grams"}:
        ounces = value / _GRAMS_PER_OUNCE
        return f"NET WT. {_format_ounces(ounces)} OZ"
    if unit in {"oz", "ounce", "ounces"}:
        return f"NET WT. {_format_ounces(value)} OZ"
    return _package_size(meta, packaging)


def _one_year_after(value: date | datetime | None) -> str:
    if value is None:
        return ""
    day = value.date() if isinstance(value, datetime) else value
    try:
        return day.replace(year=day.year + 1).isoformat()
    except ValueError:
        # Feb. 29 expires Feb. 28 in the following non-leap year.
        return day.replace(year=day.year + 1, day=28).isoformat()


def _expiration_date(lot: InventoryLot, meta: dict[str, Any], coa: CoaDocument | None) -> str:
    # A matched passing COA drives the operator-approved one-year shelf-life rule.
    if coa and _coa_status(coa) == "Passed" and coa.date_tested:
        return _one_year_after(coa.date_tested)
    return _date_text(lot.expiration_at or meta.get("expiration_date") or meta.get("best_by"))


def _qr_svg(value: str, pixels: int = 180) -> str:
    if not value:
        return ""
    widget = QrCodeWidget(value)
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    scale = float(pixels) / max(width, height)
    drawing = Drawing(float(pixels), float(pixels), transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    raw = renderSVG.drawToString(drawing)
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _result_value(results: list[CoaAnalyteResult], key: str) -> float | None:
    row = next((item for item in results if item.analyte_key == key), None)
    return row.value if row else None


def _potency(meta: dict[str, Any], quality: LotQualityEvidence | None, coa: CoaDocument | None, results: list[CoaAnalyteResult]) -> str:
    entries: list[str] = []
    thca = _result_value(results, "thca")
    if thca is None:
        thca = quality.thca_percent if quality and quality.thca_percent is not None else meta.get("thca_percent")
    total_thc = coa.total_thc_percent if coa and coa.total_thc_percent is not None else (quality.total_thc_percent if quality else meta.get("total_thc_percent"))
    tac = coa.total_cannabinoids_percent if coa and coa.total_cannabinoids_percent is not None else (quality.tac_percent if quality and quality.tac_percent is not None else meta.get("tac_percent"))
    terpenes = coa.total_terpenes_percent if coa and coa.total_terpenes_percent is not None else (quality.total_terpenes_percent if quality and quality.total_terpenes_percent is not None else meta.get("total_terpenes_percent"))
    for label, value in (("THCA", thca), ("Total THC", total_thc), ("TAC", tac), ("Total terpenes", terpenes)):
        formatted = _percent(value)
        if formatted:
            entries.append(f"{label} {formatted}")
    return " · ".join(entries)


def _raw_text(label: dict[str, str]) -> str:
    return "\n".join(label[key] for key in _LABEL_ORDER if label.get(key))


def _coa_reference(coa: CoaDocument | None) -> str:
    if coa is None:
        return ""
    return _text(coa.lab_id) or _text(coa.filename) or coa.fingerprint[:12]


def _coa_status(coa: CoaDocument | None) -> str:
    if coa is None:
        return ""
    status = _text(coa.overall_status).casefold()
    if status in {"pass", "passed"}:
        return "Passed"
    if status in {"fail", "failed"}:
        return "Failed"
    return ""


def _result_payload(row: CoaAnalyteResult) -> dict[str, Any]:
    return {
        "analysis": row.analysis,
        "key": row.analyte_key,
        "name": row.name,
        "value": row.value,
        "value_text": row.value_text,
        "units": row.units,
        "mg_g": row.mg_g,
        "limit": row.limit_value,
        "lod": row.lod,
        "loq": row.loq,
        "status": row.status,
    }


class LabelInventoryService:
    """Read inventory label candidates within one tenant/facility boundary."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.coas = CoaDocumentService(engine)

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
                ProductPackagingProfile,
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
            .outerjoin(
                ProductPackagingProfile,
                (ProductPackagingProfile.product_id == Product.id)
                & (ProductPackagingProfile.organization_id == organization_id),
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
            output: list[dict[str, Any]] = []
            for row in rows:
                lot = row[0]
                coa, results = self.coas.resolve_for_lot(session, lot)
                pending, pending_results = (None, []) if coa else self._pending_coa(session, lot)
                output.append(self._source(*row, coa, results, pending, pending_results))
            return output

    def get_source(self, organization_id: str, facility_id: str, lot_id: str) -> dict[str, Any]:
        row = next((item for item in self.list_sources(organization_id, facility_id) if item["lot_id"] == lot_id), None)
        if row is None:
            raise ValueError("Inventory batch was not found in the active facility or has no on-hand balance.")
        return row

    @staticmethod
    def _pending_coa(session: Session, lot: InventoryLot) -> tuple[CoaDocument | None, list[CoaAnalyteResult]]:
        package_id = "".join(ch for ch in str(lot.compliance_package_id or "").upper() if ch.isalnum())
        if not package_id:
            return None, []
        row = session.scalar(
            select(CoaDocument)
            .where(
                CoaDocument.organization_id == lot.organization_id,
                CoaDocument.facility_id == lot.facility_id,
                CoaDocument.package_id == package_id,
                CoaDocument.status == "needs_confirmation",
            )
            .order_by(CoaDocument.created_at.desc())
        )
        if row is None:
            return None, []
        results = list(session.scalars(select(CoaAnalyteResult).where(CoaAnalyteResult.coa_document_id == row.id).order_by(CoaAnalyteResult.sort_order, CoaAnalyteResult.name)))
        return row, results

    @staticmethod
    def _source(
        lot: InventoryLot,
        product: Product,
        facility: Facility,
        profile: ProductMasterProfile | None,
        packaging: ProductPackagingProfile | None,
        quality: LotQualityEvidence | None,
        balance: float,
        coa: CoaDocument | None,
        results: list[CoaAnalyteResult],
        pending: CoaDocument | None,
        pending_results: list[CoaAnalyteResult],
    ) -> dict[str, Any]:
        meta = _metadata(lot)
        package_id = _text(lot.compliance_package_id) or _first(meta, "source_tracking_number", "package_id", "metrc_package_id", "traceability_package_id")
        lab_state = _coa_status(coa) or _text(quality.lab_testing_state if quality else "") or _first(meta, "lab_testing_state")
        coa_reference = _coa_reference(coa) or _text(quality.coa_reference if quality else "") or _first(meta, "coa_reference")
        coa_url = (f"/api/v1/label-printing/coas/{coa.id}/file" if coa else "") or _text(quality.coa_url if quality else "") or _first(meta, "coa_url", "certificate_url", "lab_report_url")
        profile_category = (profile.category or profile.product_format) if profile else ""
        total_thc = coa.total_thc_percent if coa else (quality.total_thc_percent if quality else meta.get("total_thc_percent"))
        total_cbd = coa.total_cbd_percent if coa else (quality.total_cbd_percent if quality else meta.get("total_cbd_percent"))
        total_cannabinoids = coa.total_cannabinoids_percent if coa else (quality.total_cannabinoids_percent if quality else meta.get("total_cannabinoids_percent") or meta.get("tac_percent"))
        total_terpenes = coa.total_terpenes_percent if coa else (quality.total_terpenes_percent if quality else meta.get("total_terpenes_percent"))
        warning_text = _text(packaging.warning_text if packaging else "") or _first(meta, "warning_text", "warnings", "required_warning")
        label = {
            "product_name": _text(product.name),
            "brand": _profile_or_meta(profile.brand if profile else "", meta, "brand"),
            "strain": _profile_or_meta(profile.strain if profile else "", meta, "strain") or _text(coa.strain_name if coa else ""),
            "product_type": (_text(profile_category) or _text(coa.product_type if coa else "") or _first(meta, "category", "product_type") or product.item_type.replace("_", " ")).title(),
            "package_size": _package_size(meta, packaging),
            "net_contents": _net_contents(meta, packaging),
            "license_number": _text(facility.license_number),
            "facility_name": _text(facility.name),
            "manufacturer": _profile_or_meta(profile.manufacturer if profile else "", meta, "manufacturer"),
            "package_id": package_id,
            "batch_number": _text(coa.batch_number if coa else "") or _first(meta, "batch_number", "batch_name", "source_lot_code") or _text(lot.lot_code),
            "sku": _text(product.sku),
            "upc": _text(product.upc),
            "potency": _potency(meta, quality, coa, results),
            "total_thc": _percent(total_thc),
            "total_cbd": _percent(total_cbd),
            "total_cannabinoids": _percent(total_cannabinoids),
            "total_terpenes": _percent(total_terpenes),
            "lab_testing_state": lab_state,
            "laboratory": _text(coa.lab_name if coa else "") or _first(meta, "laboratory", "lab_name", "testing_laboratory"),
            "test_date": _date_text(coa.date_tested if coa else None) or _date_text(meta.get("analysis_date") or meta.get("test_date") or (quality.verified_at if quality else None)),
            "coa_reference": coa_reference,
            "coa_url": coa_url,
            "ingredients": _first(meta, "ingredients", "ingredient_statement"),
            "allergens": _first(meta, "allergens", "allergen_statement"),
            "harvest_date": _date_text(meta.get("harvest_date") or meta.get("harvested_at")),
            "manufacture_date": _date_text(meta.get("manufacture_date") or meta.get("manufactured_at")),
            "package_date": _date_text(meta.get("package_date") or meta.get("packaged_at")),
            "expiration_date": _expiration_date(lot, meta, coa),
            "warning_text": warning_text,
            "universal_symbol": _first(meta, "universal_symbol", "universal_symbol_text"),
            "qr_value": package_id,
        }
        active_results = results if coa else pending_results
        coa_row = coa or pending
        structured_coa = {
            "available": coa is not None,
            "lookup_key": package_id,
            "fallback_allowed": coa is None and pending is None,
            "needs_confirmation": pending is not None and coa is None,
            "document_id": coa_row.id if coa_row else "",
            "source": coa_row.source if coa_row else "",
            "status": coa_row.status if coa_row else "missing",
            "verification_state": coa_row.verification_state if coa_row else "missing",
            "filename": coa_row.filename if coa_row else "",
            "file_url": f"/api/v1/label-printing/coas/{coa_row.id}/file" if coa_row else "",
            "lab_name": coa_row.lab_name if coa_row else "",
            "lab_license_number": coa_row.lab_license_number if coa_row else "",
            "lab_id": coa_row.lab_id if coa_row else "",
            "metrc_source_id": coa_row.metrc_source_id if coa_row else "",
            "metrc_lab_id": coa_row.metrc_lab_id if coa_row else "",
            "date_tested": _date_text(coa_row.date_tested if coa_row else None),
            "overall_status": coa_row.overall_status if coa_row else "",
            "total_thc": coa_row.total_thc_percent if coa_row else None,
            "total_cbd": coa_row.total_cbd_percent if coa_row else None,
            "total_cannabinoids": coa_row.total_cannabinoids_percent if coa_row else None,
            "total_terpenes": coa_row.total_terpenes_percent if coa_row else None,
            "results": [_result_payload(item) for item in active_results],
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
            "coa": structured_coa,
            "qr": {"value": package_id, "svg": _qr_svg(package_id)},
            "raw_text": _raw_text(label),
            "source_summary": {
                "facility": facility.name,
                "license_number": facility.license_number,
                "license_type": facility.license_type,
                "qa_source": f"coa:{coa.source}" if coa else (quality.evidence_source if quality else _text(meta.get("quality_evidence_source") or "inventory metadata")),
                "coa_source": coa.source if coa else "",
                "coa_verification": coa.verification_state if coa else (pending.verification_state if pending else "missing"),
            },
        }
