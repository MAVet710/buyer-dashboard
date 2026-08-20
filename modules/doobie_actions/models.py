"""Durable Recommend → Preview → Approve → Execute action records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class ActionProposal(TimestampMixin, Base):
    __tablename__ = "action_proposals"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_action_proposal_org_idempotency"),
        CheckConstraint("risk_level in ('low','medium','high','compliance')", name="ck_action_proposal_risk"),
        CheckConstraint("status in ('proposed','approved','executing','executed','rejected','failed','expired')", name="ck_action_proposal_status"),
        CheckConstraint("financial_impact_usd >= 0", name="ck_action_proposal_financial_impact"),
        Index("ix_action_proposal_facility_status", "facility_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    preview_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    financial_impact_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionExecution(Base):
    __tablename__ = "action_executions"
    __table_args__ = (
        UniqueConstraint("proposal_id", "attempt_number", name="uq_action_execution_attempt"),
        CheckConstraint("status in ('started','succeeded','failed')", name="ck_action_execution_status"),
        Index("ix_action_execution_proposal_time", "proposal_id", "started_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("action_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="started")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
