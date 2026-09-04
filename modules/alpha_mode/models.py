from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class AlphaOperatingMode(TimestampMixin, Base):
    """Explicit alpha-stage provider mode for one DoobieLogic facility.

    Existing facilities may intentionally have no row. The service interprets
    that as a backwards-compatible automatic choice based on verified sandbox
    regulatory mappings. Once an administrator chooses a mode, the row becomes
    the durable override until changed again.
    """

    __tablename__ = "alpha_operating_modes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            name="uq_alpha_operating_mode_facility",
        ),
        CheckConstraint(
            "mode in ('doobielogic_sandbox','metrc_sandbox')",
            name="ck_alpha_operating_mode_mode",
        ),
        Index("ix_alpha_operating_mode_scope", "organization_id", "facility_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
