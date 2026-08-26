"""Durable models for DoobieLogic operational moats.

These records deliberately reference the canonical organization/facility/product/partner
models instead of creating parallel inventory, production, or commercial ledgers.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class SOPDocument(TimestampMixin, Base):
    __tablename__ = "sop_documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", "version", name="uq_sop_document_version"),
        CheckConstraint("status in ('draft','active','retired')", name="ck_sop_document_status"),
        Index("ix_sop_document_org_status", "organization_id", "status", "code"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_reference: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    required_roles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    control_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SOPAcknowledgement(Base):
    __tablename__ = "sop_acknowledgements"
    __table_args__ = (
        UniqueConstraint("sop_document_id", "user_id", name="uq_sop_ack_user"),
        Index("ix_sop_ack_org_user", "organization_id", "user_id", "acknowledged_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    sop_document_id: Mapped[str] = mapped_column(ForeignKey("sop_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    acknowledgement_text: Mapped[str] = mapped_column(String(512), nullable=False, default="Reviewed and acknowledged")


class SOPDeviation(Base):
    __tablename__ = "sop_deviations"
    __table_args__ = (
        CheckConstraint("severity in ('low','medium','high','critical')", name="ck_sop_deviation_severity"),
        CheckConstraint("status in ('open','investigating','resolved','dismissed')", name="ck_sop_deviation_status"),
        Index("ix_sop_deviation_facility_status", "facility_id", "status", "detected_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    sop_document_id: Mapped[str] = mapped_column(ForeignKey("sop_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    detected_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    resolution: Mapped[str] = mapped_column(Text, nullable=False, default="")


class LabelTemplate(TimestampMixin, Base):
    __tablename__ = "label_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", "version", name="uq_label_template_version"),
        CheckConstraint("status in ('draft','active','retired')", name="ck_label_template_status"),
        Index("ix_label_template_org_status", "organization_id", "status", "name"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    license_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    layout_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabelReview(Base):
    __tablename__ = "label_reviews"
    __table_args__ = (
        CheckConstraint("status in ('pass','warning','fail')", name="ck_label_review_status"),
        Index("ix_label_review_facility_time", "facility_id", "reviewed_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("label_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("coman_products.id", ondelete="SET NULL"), nullable=True, index=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    findings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    rule_set_reference: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MachineTelemetryEvent(Base):
    __tablename__ = "machine_telemetry_events"
    __table_args__ = (
        CheckConstraint("event_type in ('heartbeat','running','idle','downtime','fault','measurement','cycle')", name="ck_machine_telemetry_type"),
        Index("ix_machine_telemetry_machine_time", "machine_id", "recorded_at"),
        Index("ix_machine_telemetry_facility_time", "facility_id", "recorded_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("coman_facility_machines.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="manual")
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CultivationHarvest(TimestampMixin, Base):
    __tablename__ = "cultivation_harvests"
    __table_args__ = (
        UniqueConstraint("facility_id", "harvest_code", name="uq_cultivation_harvest_code"),
        CheckConstraint("status in ('planned','active','drying','completed','cancelled')", name="ck_cultivation_harvest_status"),
        Index("ix_cultivation_harvest_facility_status", "facility_id", "status", "harvested_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    harvest_code: Mapped[str] = mapped_column(String(120), nullable=False)
    strain: Mapped[str] = mapped_column(String(160), nullable=False)
    room: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    plant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wet_weight_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dry_weight_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    waste_weight_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    labor_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="planned")
    harvested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class PartnerPortalAccess(TimestampMixin, Base):
    __tablename__ = "partner_portal_access"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_partner_portal_token_hash"),
        Index("ix_partner_portal_partner_active", "partner_id", "revoked_at", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False, default="Retailer Portal")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceAccount(TimestampMixin, Base):
    __tablename__ = "service_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_service_account_name"),
        UniqueConstraint("token_hash", name="uq_service_account_token_hash"),
        Index("ix_service_account_org_active", "organization_id", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookSubscription(TimestampMixin, Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        CheckConstraint("status in ('active','paused','disabled')", name="ck_webhook_subscription_status"),
        Index("ix_webhook_subscription_org_status", "organization_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    event_types_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint("status in ('queued','sending','succeeded','failed','dead_letter')", name="ck_webhook_delivery_status"),
        Index("ix_webhook_delivery_status_time", "status", "created_at"),
        Index("ix_webhook_delivery_subscription_time", "subscription_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
