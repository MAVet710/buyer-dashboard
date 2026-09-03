"""Durable inventory-driven production labeling for Label Studio.

This workflow intentionally runs beside the existing testing/manual Label Studio.
Operators choose source inventory, a finished Product Master item and quantity;
DoobieLogic snapshots the verified source/COA and finished-product package facts,
then binds one scanned METRC package tag to the finished package.  Retail label
copies share that finished-package traceability identity.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_DOWN
import json
from typing import Any

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.services.label_studio_fast import FastLabelInventoryService
from modules.coman.models import Base, InventoryLot, Product, TimestampMixin, new_id, utc_now
from modules.product_master.models import ProductMasterProfile
from modules.product_master.packaging import ProductPackagingProfile


RUN_STATUSES = ("draft", "validated", "tagged", "printed", "applied", "released", "fulfilled", "archived")
_ALLOWED_TRANSITIONS = {
    "printed": {"applied"},
    "applied": {"released"},
    "released": {"fulfilled"},
    "fulfilled": {"archived"},
}
_GRAMS_PER_OUNCE = Decimal("28.349523125")
_OUNCE_QUANTUM = Decimal("0.00001")


class LabelProductionRun(TimestampMixin, Base):
    __tablename__ = "label_production_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "metrc_package_tag", name="uq_label_production_org_metrc_tag"),
        CheckConstraint(
            "status in ('draft','validated','tagged','printed','applied','released','fulfilled','archived')",
            name="ck_label_production_run_status",
        ),
        CheckConstraint("quantity > 0", name="ck_label_production_run_quantity_positive"),
        CheckConstraint("expected_material_quantity >= 0", name="ck_label_production_expected_nonnegative"),
        Index("ix_label_production_facility_status", "facility_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_material_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_material_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    metrc_package_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    printed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tag_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabelProductionSource(Base):
    __tablename__ = "label_production_sources"
    __table_args__ = (
        UniqueConstraint("run_id", "source_lot_id", name="uq_label_production_run_source"),
        CheckConstraint("planned_quantity >= 0", name="ck_label_production_source_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("label_production_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_lot_id: Mapped[str] = mapped_column(ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True)
    planned_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class LabelProductionEvent(Base):
    __tablename__ = "label_production_events"
    __table_args__ = (Index("ix_label_production_event_run_time", "run_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("label_production_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    from_status: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    to_status: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number_text(value: float) -> str:
    return f"{float(value):g}"


def _format_ounces(grams: float) -> str:
    ounces = Decimal(str(grams)) / _GRAMS_PER_OUNCE
    text = f"{ounces.quantize(_OUNCE_QUANTUM, rounding=ROUND_DOWN):.5f}"
    return text[1:] if text.startswith("0.") else text


def _product_unit_label(profile: ProductMasterProfile | None) -> str:
    kind = _text(profile.product_format if profile else "").casefold().replace("_", " ")
    if "pre-roll" in kind or "pre roll" in kind or "preroll" in kind:
        return "Pre-Rolls"
    if "capsule" in kind:
        return "Capsules"
    if "gumm" in kind or "edible" in kind:
        return "Pieces"
    if "vape" in kind or "cartridge" in kind:
        return "Units"
    return "Units"


def _package_fields(packaging: ProductPackagingProfile, profile: ProductMasterProfile | None) -> tuple[str, str, str]:
    value = float(packaging.net_content or 0)
    unit = _text(packaging.net_content_unit).casefold()
    package_size = f"{_number_text(value)} {unit}".strip()
    if unit in {"g", "gram", "grams"}:
        net_contents = f"NET WT. {_format_ounces(value)} OZ"
    else:
        net_contents = package_size
    count = float(packaging.units_per_package or 0)
    composition = ""
    if count > 1 and value > 0:
        each = value / count
        each_text = f"{_number_text(each)}{unit}" if unit else _number_text(each)
        composition = f"{_number_text(count)} x {each_text} {_product_unit_label(profile)}"
    return package_size, net_contents, composition


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


def _barcode_svg(value: str) -> str:
    if not value:
        return ""
    drawing = createBarcodeDrawing("Code128", value=value, humanReadable=True, barHeight=34, barWidth=0.55, quiet=True)
    raw = renderSVG.drawToString(drawing)
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _expected_material(quantity: int, packaging: ProductPackagingProfile, source_unit: str) -> tuple[float, str]:
    amount = float(packaging.net_content or 0) * quantity
    package_unit = _text(packaging.net_content_unit).casefold()
    source = _text(source_unit).casefold()
    gram_units = {"g", "gram", "grams"}
    ounce_units = {"oz", "ounce", "ounces"}
    if package_unit in gram_units and source in ounce_units:
        return float(Decimal(str(amount)) / _GRAMS_PER_OUNCE), source_unit
    if package_unit in ounce_units and source in gram_units:
        return float(Decimal(str(amount)) * _GRAMS_PER_OUNCE), source_unit
    return amount, source_unit or package_unit


class LabelProductionWorkflowService:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _event(session: Session, run: LabelProductionRun, event_type: str, actor: str, *, from_status: str = "", to_status: str = "", details: dict[str, Any] | None = None) -> None:
        session.add(LabelProductionEvent(
            organization_id=run.organization_id,
            facility_id=run.facility_id,
            run_id=run.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            details_json=json.dumps(details or {}, sort_keys=True),
        ))

    @staticmethod
    def _snapshot(run: LabelProductionRun) -> dict[str, Any]:
        try:
            value = json.loads(run.label_snapshot_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _scoped_run(self, session: Session, organization_id: str, facility_id: str, run_id: str) -> LabelProductionRun:
        row = session.get(LabelProductionRun, run_id)
        if not row or row.organization_id != organization_id or row.facility_id != facility_id:
            raise ValueError("Label production run was not found in this facility.")
        return row

    def _serialize(self, session: Session, run: LabelProductionRun) -> dict[str, Any]:
        snapshot = self._snapshot(run)
        sources = session.scalars(select(LabelProductionSource).where(LabelProductionSource.run_id == run.id)).all()
        events = session.scalars(select(LabelProductionEvent).where(LabelProductionEvent.run_id == run.id).order_by(LabelProductionEvent.occurred_at, LabelProductionEvent.id)).all()
        tag = _text(run.metrc_package_tag)
        return {
            "id": run.id,
            "organization_id": run.organization_id,
            "facility_id": run.facility_id,
            "product_id": run.product_id,
            "quantity": run.quantity,
            "expected_material_quantity": run.expected_material_quantity,
            "expected_material_unit": run.expected_material_unit,
            "status": run.status,
            "metrc_package_tag": tag,
            "created_by": run.created_by,
            "printed_by": run.printed_by,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "validated_at": run.validated_at,
            "tag_assigned_at": run.tag_assigned_at,
            "printed_at": run.printed_at,
            "applied_at": run.applied_at,
            "released_at": run.released_at,
            "fulfilled_at": run.fulfilled_at,
            "archived_at": run.archived_at,
            "snapshot": snapshot,
            "traceability": {
                "value": tag,
                "qr": {"value": tag, "svg": _qr_svg(tag)} if tag else {"value": "", "svg": ""},
                "barcode": {"value": tag, "format": "Code128", "svg": _barcode_svg(tag)} if tag else {"value": "", "format": "Code128", "svg": ""},
            },
            "sources": [{"lot_id": row.source_lot_id, "planned_quantity": row.planned_quantity, "unit": row.unit} for row in sources],
            "events": [{
                "id": event.id,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor": event.actor,
                "details": json.loads(event.details_json or "{}"),
                "occurred_at": event.occurred_at,
            } for event in events],
        }

    def create_run(self, organization_id: str, facility_id: str, *, source_lot_id: str, product_id: str, quantity: int, actor: str) -> dict[str, Any]:
        if quantity <= 0 or quantity > 500:
            raise ValueError("Finished quantity must be between 1 and 500 packages.")
        source = FastLabelInventoryService(self.engine).get_source(organization_id, facility_id, source_lot_id)
        coa = source.get("coa") or {}
        if not coa.get("available") or str(coa.get("overall_status") or "").casefold() not in {"pass", "passed"} or not coa.get("date_tested"):
            raise ValueError("The selected source must have a verified passing COA with a test date before labels can be created.")
        if coa.get("needs_confirmation"):
            raise ValueError("Confirm the selected source COA association before creating production labels.")
        with Session(self.engine) as session:
            lot = session.get(InventoryLot, source_lot_id)
            product = session.get(Product, product_id)
            packaging = session.get(ProductPackagingProfile, product_id)
            profile = session.get(ProductMasterProfile, product_id)
            if not lot or lot.organization_id != organization_id or lot.facility_id != facility_id:
                raise ValueError("Source inventory was not found in this facility.")
            if not product or product.organization_id != organization_id or not product.active:
                raise ValueError("Finished Product Master item was not found or is archived.")
            if product.item_type != "finished_good":
                raise ValueError("Choose an active finished-good Product Master item as the end product.")
            if profile is not None and not profile.production_enabled:
                raise ValueError("The selected finished product is not enabled for Production Ops.")
            if packaging is None or float(packaging.net_content or 0) <= 0 or float(packaging.units_per_package or 0) <= 0:
                raise ValueError("Configure net content and units per package in Product Master before labeling this product.")
            expected, expected_unit = _expected_material(quantity, packaging, str(source.get("inventory_unit") or ""))
            on_hand = float(source.get("on_hand") or 0)
            if expected_unit and str(source.get("inventory_unit") or "").casefold() == expected_unit.casefold() and expected > on_hand + 1e-9:
                raise ValueError(f"Source inventory is insufficient: {expected:g} {expected_unit} required but {on_hand:g} {expected_unit} is available.")
            package_size, net_contents, composition = _package_fields(packaging, profile)
            label = dict(source.get("label") or {})
            label.update({
                "product_name": product.name,
                "brand": _text(profile.brand if profile else "") or label.get("brand", ""),
                "strain": _text(profile.strain if profile else "") or label.get("strain", ""),
                "product_type": _text(profile.product_format if profile else "") or _text(profile.category if profile else "") or product.item_type.replace("_", " ").title(),
                "package_size": package_size,
                "net_contents": net_contents,
                "package_composition": composition,
                "manufacturer": _text(profile.manufacturer if profile else "") or label.get("manufacturer", ""),
                "warning_text": _text(packaging.warning_text),
                "package_id": "",
            })
            snapshot = {
                "source": {
                    "lot_id": source_lot_id,
                    "package_id": source.get("package_id", ""),
                    "lot_code": source.get("lot_code", ""),
                    "product_id": source.get("product_id", ""),
                    "product_name": source.get("product_name", ""),
                    "on_hand": on_hand,
                    "inventory_unit": source.get("inventory_unit", ""),
                    "coa": coa,
                    "source_summary": source.get("source_summary") or {},
                },
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "brand": _text(profile.brand if profile else ""),
                    "category": _text(profile.category if profile else ""),
                    "strain": _text(profile.strain if profile else ""),
                    "product_format": _text(profile.product_format if profile else ""),
                    "manufacturer": _text(profile.manufacturer if profile else ""),
                    "packaging": {
                        "net_content": packaging.net_content,
                        "net_content_unit": packaging.net_content_unit,
                        "units_per_package": packaging.units_per_package,
                        "sellable_unit": packaging.sellable_unit,
                        "case_pack": packaging.case_pack,
                        "warning_text": packaging.warning_text,
                    },
                },
                "label": label,
                "quantity": quantity,
                "expected_material_quantity": expected,
                "expected_material_unit": expected_unit,
            }
            now = utc_now()
            run = LabelProductionRun(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=product_id,
                quantity=quantity,
                expected_material_quantity=expected,
                expected_material_unit=expected_unit,
                status="draft",
                label_snapshot_json=json.dumps(snapshot, sort_keys=True),
                created_by=actor,
            )
            session.add(run)
            session.flush()
            session.add(LabelProductionSource(
                organization_id=organization_id,
                facility_id=facility_id,
                run_id=run.id,
                source_lot_id=source_lot_id,
                planned_quantity=expected,
                unit=expected_unit,
            ))
            self._event(session, run, "created", actor, to_status="draft", details={"quantity": quantity, "source_lot_id": source_lot_id, "product_id": product_id})
            run.status = "validated"
            run.validated_at = now
            self._event(session, run, "validated", actor, from_status="draft", to_status="validated", details={"coa_document_id": coa.get("document_id", ""), "coa_test_date": coa.get("date_tested", "")})
            session.commit()
            session.refresh(run)
            return self._serialize(session, run)

    def assign_tag(self, organization_id: str, facility_id: str, run_id: str, tag: str, actor: str) -> dict[str, Any]:
        clean = _text(tag)
        if len(clean) < 4 or len(clean) > 128 or any(ch.isspace() for ch in clean):
            raise ValueError("Scan a package tag between 4 and 128 characters with no spaces.")
        with Session(self.engine) as session:
            run = self._scoped_run(session, organization_id, facility_id, run_id)
            if run.status != "validated":
                raise ValueError("A METRC package tag can only be assigned after the label run has validated.")
            duplicate = session.scalar(select(LabelProductionRun.id).where(LabelProductionRun.organization_id == organization_id, LabelProductionRun.metrc_package_tag == clean, LabelProductionRun.id != run.id))
            if duplicate:
                raise ValueError("That METRC package tag is already assigned to another finished package in this organization.")
            before = run.status
            run.metrc_package_tag = clean
            run.status = "tagged"
            run.tag_assigned_at = utc_now()
            snapshot = self._snapshot(run)
            label = dict(snapshot.get("label") or {})
            label["package_id"] = clean
            snapshot["label"] = label
            snapshot["finished_package"] = {"metrc_package_tag": clean}
            run.label_snapshot_json = json.dumps(snapshot, sort_keys=True)
            self._event(session, run, "tag_assigned", actor, from_status=before, to_status="tagged", details={"metrc_package_tag": clean})
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("That METRC package tag is already assigned to another finished package in this organization.") from exc
            session.refresh(run)
            return self._serialize(session, run)

    def record_print(self, organization_id: str, facility_id: str, run_id: str, *, actor: str, copies: int | None = None, reason: str = "") -> dict[str, Any]:
        with Session(self.engine) as session:
            run = self._scoped_run(session, organization_id, facility_id, run_id)
            requested = int(copies or run.quantity)
            if requested <= 0 or requested > 500:
                raise ValueError("Print copies must be between 1 and 500.")
            if run.status == "tagged":
                run.status = "printed"
                run.printed_at = utc_now()
                run.printed_by = actor
                self._event(session, run, "printed", actor, from_status="tagged", to_status="printed", details={"copies": requested})
            elif run.status in {"printed", "applied", "released", "fulfilled"}:
                clean_reason = _text(reason)
                if not clean_reason:
                    raise ValueError("A reprint reason is required after the first print.")
                self._event(session, run, "reprinted", actor, from_status=run.status, to_status=run.status, details={"copies": requested, "reason": clean_reason})
            else:
                raise ValueError("Assign the finished METRC package tag before printing labels.")
            session.commit()
            session.refresh(run)
            return self._serialize(session, run)

    def transition(self, organization_id: str, facility_id: str, run_id: str, *, status: str, actor: str, note: str = "") -> dict[str, Any]:
        wanted = _text(status).casefold()
        with Session(self.engine) as session:
            run = self._scoped_run(session, organization_id, facility_id, run_id)
            if wanted not in _ALLOWED_TRANSITIONS.get(run.status, set()):
                raise ValueError(f"Label run cannot move from {run.status} to {wanted}.")
            before = run.status
            run.status = wanted
            now = utc_now()
            if wanted == "applied":
                run.applied_at = now
            elif wanted == "released":
                run.released_at = now
            elif wanted == "fulfilled":
                run.fulfilled_at = now
            elif wanted == "archived":
                run.archived_at = now
            self._event(session, run, wanted, actor, from_status=before, to_status=wanted, details={"note": _text(note)})
            session.commit()
            session.refresh(run)
            return self._serialize(session, run)

    def get_run(self, organization_id: str, facility_id: str, run_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            return self._serialize(session, self._scoped_run(session, organization_id, facility_id, run_id))

    def list_runs(self, organization_id: str, facility_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(select(LabelProductionRun).where(LabelProductionRun.organization_id == organization_id, LabelProductionRun.facility_id == facility_id).order_by(LabelProductionRun.created_at.desc()).limit(limit)).all()
            return [self._serialize(session, row) for row in rows]
