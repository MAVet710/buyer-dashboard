from __future__ import annotations

from datetime import date
from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from modules.coman.models import Base, TimestampMixin, new_id


class AdvisoryLead(TimestampMixin, Base):
    __tablename__ = "advisory_leads"
    __table_args__ = (
        CheckConstraint("status in ('NEW','CONTACTED','QUALIFIED','CONSULTATION_BOOKED','PROPOSAL_SENT','CLIENT','CLOSED_LOST')", name="ck_advisory_lead_status"),
        CheckConstraint("locations >= 1 AND locations <= 10000", name="ck_advisory_lead_locations"),
        UniqueConstraint("organization_id", "submission_id", name="uq_advisory_lead_submission"),
        Index("ix_advisory_lead_owner_status_created", "organization_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="RESTRICT"), nullable=False)
    submission_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    locations: Mapped[int] = mapped_column(Integer, nullable=False)
    challenge: Mapped[str] = mapped_column(String(2000), nullable=False)
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False, default="advisory-intake-v1")
    source_tool: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    score_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    attribution_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NEW")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AdvisoryDailyEvent(Base):
    __tablename__ = "advisory_daily_events"
    __table_args__ = (UniqueConstraint("organization_id", "day", "event", "placement", "item", name="uq_advisory_daily_event"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="RESTRICT"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    placement: Mapped[str] = mapped_column(String(40), nullable=False)
    item: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
