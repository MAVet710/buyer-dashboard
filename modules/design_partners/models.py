"""Design-partner program records for turning pilots into measurable case studies."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class DesignPartnerAccount(TimestampMixin, Base):
    __tablename__ = "design_partner_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_design_partner_org"),
        CheckConstraint("status in ('prospect','pilot','live','case_study','graduated','churned')", name="ck_design_partner_status"),
        Index("ix_design_partner_status", "status", "started_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="prospect")
    champion_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    champion_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    pain_profile: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_targets_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_case_study_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class DesignPartnerMetric(TimestampMixin, Base):
    __tablename__ = "design_partner_metrics"
    __table_args__ = (
        UniqueConstraint("account_id", "metric_key", name="uq_design_partner_metric_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("design_partner_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="higher")
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class DesignPartnerFeedback(TimestampMixin, Base):
    __tablename__ = "design_partner_feedback"
    __table_args__ = (
        CheckConstraint("severity in ('low','medium','high','critical')", name="ck_design_partner_feedback_severity"),
        CheckConstraint("status in ('open','planned','shipped','declined')", name="ck_design_partner_feedback_status"),
        Index("ix_design_partner_feedback_account_status", "account_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("design_partner_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="medium")
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
