"""Canonical material-transformation graph for seed-to-sale genealogy.

Inventory quantity remains authoritative in ``coman_inventory_transactions``.
These tables record why material moved from one durable entity/lot to another so
Cultivation, Production, Extraction and Package Studio can share one genealogy.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class MaterialTransformation(TimestampMixin, Base):
    __tablename__ = "material_transformations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "transformation_type",
            "source_entity_type",
            "source_entity_id",
            name="uq_material_transformation_source",
        ),
        Index(
            "ix_material_transformation_scope_type",
            "organization_id",
            "facility_id",
            "transformation_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transformation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MaterialTransformationInput(TimestampMixin, Base):
    __tablename__ = "material_transformation_inputs"
    __table_args__ = (
        UniqueConstraint(
            "transformation_id",
            "entity_type",
            "entity_id",
            "purpose",
            name="uq_material_transformation_input_entity",
        ),
        Index("ix_material_transformation_input_lot", "lot_id", "transformation_id"),
        Index("ix_material_transformation_input_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transformation_id: Mapped[str] = mapped_column(
        ForeignKey("material_transformations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lot_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="source")
    measurement_basis: Mapped[str] = mapped_column(String(24), nullable=False, default="")


class MaterialTransformationOutput(TimestampMixin, Base):
    __tablename__ = "material_transformation_outputs"
    __table_args__ = (
        UniqueConstraint("transformation_id", "lot_id", name="uq_material_transformation_output_lot"),
        Index("ix_material_transformation_output_lot", "lot_id", "transformation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transformation_id: Mapped[str] = mapped_column(
        ForeignKey("material_transformations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lot_id: Mapped[str] = mapped_column(
        ForeignKey("coman_inventory_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="standard")
    measurement_basis: Mapped[str] = mapped_column(String(24), nullable=False, default="")


class MaterialTransformationLoss(TimestampMixin, Base):
    __tablename__ = "material_transformation_losses"
    __table_args__ = (Index("ix_material_transformation_loss", "transformation_id", "loss_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transformation_id: Mapped[str] = mapped_column(
        ForeignKey("material_transformations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    loss_type: Mapped[str] = mapped_column(String(64), nullable=False, default="process_loss")
    measurement_basis: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
