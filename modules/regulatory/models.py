from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class RegulatoryFacilityMapping(TimestampMixin, Base):
    __tablename__ = "regulatory_facility_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "facility_id", "provider", "license_number", "environment",
            name="uq_regulatory_mapping_scope_license_environment",
        ),
        CheckConstraint("provider in ('metrc','biotrack')", name="ck_regulatory_mapping_provider"),
        CheckConstraint("environment in ('sandbox','production')", name="ck_regulatory_mapping_environment"),
        Index("ix_regulatory_mapping_active", "organization_id", "facility_id", "provider", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_configuration_id: Mapped[str | None] = mapped_column(ForeignKey("integration_configurations.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction_code: Mapped[str] = mapped_column(String(16), nullable=False)
    license_number: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_facility_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
