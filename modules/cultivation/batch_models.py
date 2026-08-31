from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class CultivationPlantGroup(TimestampMixin, Base):
    """Durable operator batch/group for nursery and cultivation plant work."""

    __tablename__ = "cultivation_plant_groups"
    __table_args__ = (
        UniqueConstraint("facility_id", "group_code", name="uq_cultivation_group_facility_code"),
        CheckConstraint(
            "group_type in ('clone_batch','seed_batch','nursery','vegetative','flowering')",
            name="ck_cultivation_group_type",
        ),
        CheckConstraint("status in ('active','closed','cancelled')", name="ck_cultivation_group_status"),
        Index("ix_cultivation_groups_facility_status", "facility_id", "status", "group_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    group_code: Mapped[str] = mapped_column(String(120), nullable=False)
    group_type: Mapped[str] = mapped_column(String(32), nullable=False)
    strain_name: Mapped[str] = mapped_column(String(255), nullable=False)
    room_code: Mapped[str] = mapped_column(String(120), nullable=False, default="UNASSIGNED")
    source_lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mother_plant_id: Mapped[str | None] = mapped_column(
        ForeignKey("cultivation_plants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class CultivationPlantGroupMember(Base):
    """Plant membership in a durable cultivation batch/group."""

    __tablename__ = "cultivation_plant_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "plant_id", name="uq_cultivation_group_member"),
        Index("ix_cultivation_group_members_plant", "plant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("cultivation_plant_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plant_id: Mapped[str] = mapped_column(
        ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)


class CultivationPlantParentLink(Base):
    """First-class plant genealogy edge; legacy mother tag remains display compatibility only."""

    __tablename__ = "cultivation_plant_parent_links"
    __table_args__ = (
        UniqueConstraint("child_plant_id", "relationship", name="uq_cultivation_plant_parent_relationship"),
        CheckConstraint("relationship in ('mother','source_plant')", name="ck_cultivation_parent_relationship"),
        Index("ix_cultivation_parent_links_parent", "parent_plant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    child_plant_id: Mapped[str] = mapped_column(
        ForeignKey("cultivation_plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_plant_id: Mapped[str] = mapped_column(
        ForeignKey("cultivation_plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    relationship: Mapped[str] = mapped_column(String(24), nullable=False, default="mother")
    linked_by: Mapped[str] = mapped_column(String(255), nullable=False)
