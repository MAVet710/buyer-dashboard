from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class IntegrationConfiguration(TimestampMixin, Base):
    __tablename__ = "integration_configurations"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_key", "provider", name="uq_integration_scope_provider"),
        CheckConstraint("scope_type in ('user','facility','platform')", name="ck_integration_scope_type"),
        CheckConstraint(
            "provider in ('metrc','doobie','ai_runtime','spacemail','metrc_sandbox','dutchie_sandbox','biotrack_sandbox','quickbooks_sandbox')",
            name="ck_integration_provider",
        ),
        CheckConstraint("status in ('not_connected','configured','connected','failed')", name="ck_integration_status"),
        Index("ix_integration_org_facility", "organization_id", "facility_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret_hint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_connected")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
