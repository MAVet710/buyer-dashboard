"""Facility implementation annotations and durable report delivery receipts."""
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, new_id, utc_now


class FacilityScope:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="RESTRICT"))
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"))


class ReadinessAnnotation(FacilityScope, Base):
    __tablename__ = "facility_readiness_annotations"
    __table_args__ = (
        UniqueConstraint("organization_id", "facility_id", "item_key", name="uq_readiness_item"),
        CheckConstraint("manual_status IS NULL OR manual_status IN ('complete','incomplete','not_applicable','needs_review')", name="ck_readiness_manual_status"),
    )
    item_key: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(160), default="")
    target_date: Mapped[date | None] = mapped_column(Date)
    manual_status: Mapped[str | None] = mapped_column(String(24))
    updated_by: Mapped[str] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReportSubscription(FacilityScope, Base):
    __tablename__ = "report_subscriptions"
    __table_args__ = (
        Index("ix_report_subscription_due", "organization_id", "facility_id", "active", "next_run"),
        CheckConstraint("cadence IN ('daily','weekly','monthly')", name="ck_report_subscription_cadence"),
    )
    report_type: Mapped[str] = mapped_column(String(40))
    recipients_json: Mapped[str] = mapped_column(Text)
    cadence: Mapped[str] = mapped_column(String(12))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReportDelivery(FacilityScope, Base):
    __tablename__ = "report_deliveries"
    __table_args__ = (
        UniqueConstraint("subscription_id", "run_key", name="uq_report_delivery_run"),
        Index("ix_report_delivery_history", "organization_id", "facility_id", "created_at"),
        CheckConstraint("status IN ('processing','deferred','failed','sent','needs_review')", name="ck_report_delivery_status"),
    )
    subscription_id: Mapped[str] = mapped_column(ForeignKey("report_subscriptions.id", ondelete="RESTRICT"))
    run_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), default="processing")
    detail: Mapped[str] = mapped_column(String(500), default="Delivery reserved. If interrupted, review before sending again.")
    recipients_json: Mapped[str] = mapped_column(Text)
    report_type: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
