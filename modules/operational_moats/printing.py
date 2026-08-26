"""Deterministic label printing workflow linked to LabelGuard evidence."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from modules.coman.models import Base, TimestampMixin, new_id, utc_now
from .models import LabelReview, LabelTemplate


class PrinterProfile(TimestampMixin, Base):
    __tablename__ = "printer_profiles"
    __table_args__ = (
        UniqueConstraint("facility_id", "name", name="uq_printer_profile_name"),
        CheckConstraint("transport in ('browser','edge','zpl')", name="ck_printer_profile_transport"),
        Index("ix_printer_profile_facility_active", "facility_id", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    transport: Mapped[str] = mapped_column(String(24), nullable=False, default="browser")
    printer_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    dpi: Mapped[int] = mapped_column(Integer, nullable=False, default=203)
    width_mm: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    height_mm: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class LabelPrintJob(Base):
    __tablename__ = "label_print_jobs"
    __table_args__ = (
        CheckConstraint("copies > 0 and copies <= 500", name="ck_label_print_job_copies"),
        CheckConstraint("format in ('browser','zpl')", name="ck_label_print_job_format"),
        CheckConstraint("status in ('queued','rendered','dispatched','printed','failed','cancelled')", name="ck_label_print_job_status"),
        Index("ix_label_print_job_facility_status", "facility_id", "status", "queued_at"),
        Index("ix_label_print_job_review", "label_review_id", "queued_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    printer_profile_id: Mapped[str] = mapped_column(ForeignKey("printer_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("label_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    label_review_id: Mapped[str] = mapped_column(ForeignKey("label_reviews.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("coman_products.id", ondelete="SET NULL"), nullable=True, index=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    format: Mapped[str] = mapped_column(String(24), nullable=False, default="browser")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    render_data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rendered_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    override_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    queued_by: Mapped[str] = mapped_column(String(255), nullable=False)
    dispatched_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _render_tokens(template: str, data: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = data.get(key, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value if value is not None else "")
    return re.sub(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", replace, str(template or ""))


class LabelPrintingService:
    PASS_ROLES = {"dev", "admin", "qa", "supervisor", "operator"}
    WARNING_OVERRIDE_ROLES = {"dev", "admin", "qa"}

    def __init__(self, engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def create_printer(
        self,
        *,
        organization_id: str,
        facility_id: str,
        name: str,
        actor: str,
        transport: str = "browser",
        printer_key: str = "",
        dpi: int = 203,
        width_mm: float = 50,
        height_mm: float = 25,
    ) -> PrinterProfile:
        transport = str(transport or "browser").casefold()
        if transport not in {"browser", "edge", "zpl"}:
            raise ValueError("Printer transport must be browser, edge, or zpl.")
        if not str(name or "").strip():
            raise ValueError("Printer profile name is required.")
        if dpi < 100 or dpi > 1200 or width_mm <= 0 or height_mm <= 0:
            raise ValueError("Printer dimensions or DPI are outside supported bounds.")
        with self.sessions.begin() as session:
            row = PrinterProfile(
                organization_id=organization_id,
                facility_id=facility_id,
                name=str(name).strip(),
                transport=transport,
                printer_key=str(printer_key or "").strip(),
                dpi=int(dpi),
                width_mm=float(width_mm),
                height_mm=float(height_mm),
                created_by=actor,
            )
            session.add(row)
            session.flush()
            return row

    def list_printers(self, organization_id: str, facility_id: str) -> list[PrinterProfile]:
        with self.sessions() as session:
            return list(session.scalars(select(PrinterProfile).where(PrinterProfile.organization_id == organization_id, PrinterProfile.facility_id == facility_id).order_by(PrinterProfile.name)))

    def queue_job(
        self,
        *,
        organization_id: str,
        facility_id: str,
        printer_profile_id: str,
        template_id: str,
        label_review_id: str,
        actor: str,
        role: str,
        render_data: dict[str, Any],
        copies: int = 1,
        override_reason: str = "",
    ) -> LabelPrintJob:
        role = str(role or "").casefold()
        if role not in self.PASS_ROLES:
            raise PermissionError("Your role cannot queue label printing.")
        if copies < 1 or copies > 500:
            raise ValueError("Copies must be between 1 and 500.")
        with self.sessions.begin() as session:
            printer = session.get(PrinterProfile, printer_profile_id)
            template = session.get(LabelTemplate, template_id)
            review = session.get(LabelReview, label_review_id)
            if not printer or printer.organization_id != organization_id or printer.facility_id != facility_id or not printer.active:
                raise ValueError("Active printer profile was not found in this facility.")
            if not template or template.organization_id != organization_id or (template.facility_id and template.facility_id != facility_id):
                raise ValueError("Label template was not found in this organization/facility.")
            if template.status != "active":
                raise ValueError("Only an active, approved label template can be printed.")
            if not review or review.organization_id != organization_id or review.facility_id != facility_id:
                raise ValueError("LabelGuard review was not found in this facility.")
            if review.template_id != template.id:
                raise ValueError("LabelGuard review must reference the selected template version.")
            if review.status == "fail":
                raise ValueError("LabelGuard failed this label. Printing is blocked until the label passes review.")
            clean_override = str(override_reason or "").strip()
            if review.status == "warning" and (role not in self.WARNING_OVERRIDE_ROLES or len(clean_override) < 3):
                raise PermissionError("Warning labels require a QA/Admin/DEV override reason before printing.")
            layout = _load_json(template.layout_json, {})
            output_format = "zpl" if printer.transport == "zpl" else "browser"
            template_text = str(layout.get("zpl_template") if output_format == "zpl" else layout.get("template") or layout.get("html_template") or "")
            if not template_text:
                raise ValueError(f"The active template does not contain a {output_format} render template.")
            rendered = _render_tokens(template_text, dict(render_data or {}))
            row = LabelPrintJob(
                organization_id=organization_id,
                facility_id=facility_id,
                printer_profile_id=printer.id,
                template_id=template.id,
                label_review_id=review.id,
                product_id=review.product_id,
                package_id=review.package_id,
                copies=int(copies),
                format=output_format,
                status="rendered" if printer.transport == "browser" else "queued",
                render_data_json=json.dumps(render_data or {}, default=str, sort_keys=True),
                rendered_content=rendered,
                override_reason=clean_override,
                queued_by=actor,
            )
            session.add(row)
            session.flush()
            return row

    def list_jobs(self, organization_id: str, facility_id: str, *, statuses: tuple[str, ...] = (), limit: int = 250) -> list[LabelPrintJob]:
        with self.sessions() as session:
            statement = select(LabelPrintJob).where(LabelPrintJob.organization_id == organization_id, LabelPrintJob.facility_id == facility_id)
            if statuses:
                statement = statement.where(LabelPrintJob.status.in_(statuses))
            return list(session.scalars(statement.order_by(LabelPrintJob.queued_at.desc()).limit(max(1, min(limit, 1000)))))

    def claim_edge_job(self, organization_id: str, facility_id: str, job_id: str, actor: str) -> LabelPrintJob:
        with self.sessions.begin() as session:
            row = session.get(LabelPrintJob, job_id)
            if not row or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("Print job was not found in this facility.")
            if row.status != "queued":
                raise ValueError("Only queued edge/ZPL jobs can be claimed.")
            row.status = "dispatched"
            row.dispatched_by = actor
            row.dispatched_at = utc_now()
            session.flush()
            return row

    def complete_job(self, organization_id: str, facility_id: str, job_id: str, actor: str, *, success: bool, error: str = "") -> LabelPrintJob:
        with self.sessions.begin() as session:
            row = session.get(LabelPrintJob, job_id)
            if not row or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("Print job was not found in this facility.")
            if row.status not in {"rendered", "dispatched"}:
                raise ValueError("Only rendered/dispatched jobs can be completed.")
            row.status = "printed" if success else "failed"
            row.dispatched_by = row.dispatched_by or actor
            row.dispatched_at = row.dispatched_at or utc_now()
            row.completed_at = utc_now()
            row.last_error = "" if success else str(error or "Print failed")[:2000]
            session.flush()
            return row
