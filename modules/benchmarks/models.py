"""Privacy-safe aggregate benchmark storage for the Buyer Dash network moat."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modules.coman.models import Base, TimestampMixin, new_id, utc_now


class BenchmarkSetting(TimestampMixin, Base):
    __tablename__ = "benchmark_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_benchmark_setting_org"),
        CheckConstraint("minimum_cohort_size >= 3 and minimum_cohort_size <= 50", name="ck_benchmark_min_cohort"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    share_anonymized_aggregates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    minimum_cohort_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class BenchmarkObservation(Base):
    """Aggregated metric only: no product names, customers, tags, or raw run rows."""

    __tablename__ = "benchmark_observations"
    __table_args__ = (
        UniqueConstraint("facility_id", "metric_key", "cohort_key", "period_start", "period_end", name="uq_benchmark_observation_period"),
        CheckConstraint("sample_count >= 1", name="ck_benchmark_sample_count"),
        Index("ix_benchmark_metric_cohort_period", "metric_key", "cohort_key", "period_end"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    cohort_key: Mapped[str] = mapped_column(String(160), nullable=False, default="all")
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
