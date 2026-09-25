"""Relationship records reference canonical trade partners and commercial orders."""
from datetime import date
from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from modules.coman.models import Base, TimestampMixin, new_id

class RelationshipScope(TimestampMixin):
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id"), nullable=False)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(ForeignKey("commercial_trade_partners.id"), nullable=False)

class NextAction:
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id", ondelete="SET NULL"))
    next_action: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    next_action_date: Mapped[date | None] = mapped_column(Date)

class CustomerRelationship(RelationshipScope, NextAction, Base):
    __tablename__ = "commercial_customer_relationships"
    __table_args__ = (UniqueConstraint("organization_id", "facility_id", "partner_id", name="uq_crm_account_scope"),
        CheckConstraint("status in ('prospect','active','on_hold','inactive')", name="ck_crm_account_status"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="prospect")

class CommercialOpportunity(RelationshipScope, NextAction, Base):
    __tablename__ = "commercial_opportunities"
    __table_args__ = (Index("ix_crm_opportunity_scope_stage", "organization_id", "facility_id", "stage", "created_at"),
        CheckConstraint("stage in ('lead','qualified','quoted','negotiating','won','lost')", name="ck_crm_opportunity_stage"),
        CheckConstraint("estimated_value >= 0", name="ck_crm_opportunity_value"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="lead")
    estimated_value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="")

class CommercialActivity(RelationshipScope, Base):
    __tablename__ = "commercial_activities"
    __table_args__ = (Index("ix_crm_activity_timeline", "organization_id", "facility_id", "partner_id", "created_at"),
        CheckConstraint("kind in ('call','email','meeting','note','task_reference')", name="ck_crm_activity_kind"))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)

class CommercialQuote(RelationshipScope, Base):
    __tablename__ = "commercial_quotes"
    __table_args__ = (Index("ix_crm_quote_scope_customer", "organization_id", "facility_id", "partner_id", "created_at"),
        CheckConstraint("status in ('draft','converted')", name="ck_crm_quote_status"),
        UniqueConstraint("commercial_order_id", name="uq_crm_quote_order"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_opportunities.id"))
    commercial_order_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_orders.id"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    lines_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
