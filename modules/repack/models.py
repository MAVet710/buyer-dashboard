"""Planning documents only. Production and inventory remain canonical."""
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id


class WhiteLabelPlan(TimestampMixin, Base):
    __tablename__ = "white_label_plans"
    __table_args__ = (
        CheckConstraint("status in ('draft','approved','cancelled')", name="ck_white_label_plan_status"),
        Index("ix_white_label_plan_scope", "organization_id", "facility_id", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id"), nullable=False)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id"), nullable=False)
    source_lot_id: Mapped[str] = mapped_column(ForeignKey("coman_inventory_lots.id"), nullable=False)
    production_order_id: Mapped[str | None] = mapped_column(ForeignKey("coman_production_orders.id"), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scenario_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_json: Mapped[str] = mapped_column(Text, nullable=False)
    economics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
