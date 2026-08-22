from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class RetailPlanningPolicy(TimestampMixin, Base):
    __tablename__ = "retail_planning_policies"
    __table_args__ = (
        UniqueConstraint("facility_id", "product_id", name="uq_retail_planning_facility_product"),
        CheckConstraint("target_doh >= 0", name="ck_retail_planning_target_doh"),
        CheckConstraint("safety_stock >= 0", name="ck_retail_planning_safety_stock"),
        CheckConstraint("minimum_order_quantity >= 0", name="ck_retail_planning_moq"),
        CheckConstraint("case_pack >= 0", name="ck_retail_planning_case_pack"),
        CheckConstraint("velocity_window_days between 7 and 180", name="ck_retail_planning_velocity_window"),
        Index("ix_retail_planning_org_facility_active", "organization_id", "facility_id", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("coman_products.id", ondelete="CASCADE"), nullable=False, index=True)
    preferred_vendor_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_trade_partners.id", ondelete="SET NULL"), nullable=True, index=True)
    target_doh: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    safety_stock: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reorder_point: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    minimum_order_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    case_pack: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    velocity_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
