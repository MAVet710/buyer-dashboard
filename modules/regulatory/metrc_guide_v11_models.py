from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class MetrcHarvestWasteProjection(TimestampMixin, Base):
    """Audit-safe link between a Metrc harvest-waste entry and material loss.

    Metrc's 2021 generic guide allows a harvested waste entry to be discontinued,
    which removes that waste from Metrc and restores its weight to the harvest.
    DoobieLogic preserves the original waste record and marks this projection as
    discontinued rather than erasing operational history.
    """

    __tablename__ = "metrc_harvest_waste_projections"
    __table_args__ = (
        UniqueConstraint("waste_record_id", name="uq_metrc_harvest_waste_projection_waste"),
        UniqueConstraint("material_loss_id", name="uq_metrc_harvest_waste_projection_loss"),
        Index("ix_metrc_harvest_waste_projection_scope", "organization_id", "facility_id", "discontinued_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    waste_record_id: Mapped[str] = mapped_column(
        ForeignKey("cultivation_waste_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_loss_id: Mapped[str] = mapped_column(
        ForeignKey("material_transformation_losses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discontinued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discontinued_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
