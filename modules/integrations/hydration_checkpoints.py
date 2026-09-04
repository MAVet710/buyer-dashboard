from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from modules.coman.models import Base, new_id, utc_now


class IntegrationHydrationPageCheckpoint(Base):
    """Durable provider page captured during one incomplete hydration generation.

    Pages are never promoted directly to the current-provider snapshot. A complete
    generation is assembled first; only then may the existing snapshot replacement
    layer mark provider membership current. This prevents a mid-import failure from
    making a partial page set look like regulatory truth.
    """

    __tablename__ = "integration_hydration_page_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "resource_key",
            "generation_id",
            "page_number",
            name="uq_integration_hydration_page",
        ),
        Index(
            "ix_integration_hydration_page_resume",
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "resource_key",
            "completed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("coman_facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="metrc")
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_key: Mapped[str] = mapped_column(String(160), nullable=False)
    generation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    page_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    records_json: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def page_fingerprint(records: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_json(records).encode("utf-8")).hexdigest()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class IntegrationHydrationCheckpointRepository:
    """Resume journal for provider pagination with short-lived anchor validation."""

    def __init__(self, engine, *, resume_ttl_minutes: int = 30):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.resume_ttl = timedelta(minutes=max(1, int(resume_ttl_minutes)))

    def latest_incomplete(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        environment: str,
        resource_key: str,
    ) -> dict[str, Any] | None:
        with self.sessions() as session:
            latest = session.scalar(
                select(IntegrationHydrationPageCheckpoint)
                .where(
                    IntegrationHydrationPageCheckpoint.organization_id == organization_id,
                    IntegrationHydrationPageCheckpoint.facility_id == facility_id,
                    IntegrationHydrationPageCheckpoint.provider == provider,
                    IntegrationHydrationPageCheckpoint.environment == environment,
                    IntegrationHydrationPageCheckpoint.resource_key == resource_key,
                )
                .order_by(IntegrationHydrationPageCheckpoint.completed_at.desc())
                .limit(1)
            )
            if latest is None:
                return None
            completed_at = _aware(latest.completed_at)
            if completed_at is None or utc_now() - completed_at > self.resume_ttl:
                return None
            rows = list(
                session.scalars(
                    select(IntegrationHydrationPageCheckpoint)
                    .where(
                        IntegrationHydrationPageCheckpoint.organization_id == organization_id,
                        IntegrationHydrationPageCheckpoint.facility_id == facility_id,
                        IntegrationHydrationPageCheckpoint.provider == provider,
                        IntegrationHydrationPageCheckpoint.environment == environment,
                        IntegrationHydrationPageCheckpoint.resource_key == resource_key,
                        IntegrationHydrationPageCheckpoint.generation_id == latest.generation_id,
                    )
                    .order_by(IntegrationHydrationPageCheckpoint.page_number)
                )
            )
        if not rows:
            return None
        total_pages = max(int(row.total_pages or 1) for row in rows)
        max_page = max(int(row.page_number or 0) for row in rows)
        if max_page >= total_pages:
            return None
        contiguous = [row.page_number for row in rows] == list(range(1, max_page + 1))
        if not contiguous:
            return None
        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row.records_json or "[]")
            except (TypeError, json.JSONDecodeError):
                return None
            if not isinstance(payload, list):
                return None
            records.extend(dict(item) for item in payload if isinstance(item, dict))
        return {
            "generation_id": latest.generation_id,
            "next_page": max_page + 1,
            "total_pages": total_pages,
            "first_page_fingerprint": rows[0].page_fingerprint,
            "records": records,
            "last_checkpoint_at": latest.completed_at,
        }

    def new_generation(self) -> str:
        return str(uuid.uuid4())

    def save_page(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        environment: str,
        resource_key: str,
        generation_id: str,
        page_number: int,
        total_pages: int,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fingerprint = page_fingerprint(records)
        with self.sessions.begin() as session:
            row = session.scalar(
                select(IntegrationHydrationPageCheckpoint).where(
                    IntegrationHydrationPageCheckpoint.organization_id == organization_id,
                    IntegrationHydrationPageCheckpoint.facility_id == facility_id,
                    IntegrationHydrationPageCheckpoint.provider == provider,
                    IntegrationHydrationPageCheckpoint.environment == environment,
                    IntegrationHydrationPageCheckpoint.resource_key == resource_key,
                    IntegrationHydrationPageCheckpoint.generation_id == generation_id,
                    IntegrationHydrationPageCheckpoint.page_number == page_number,
                )
            )
            if row is None:
                row = IntegrationHydrationPageCheckpoint(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    provider=provider,
                    environment=environment,
                    resource_key=resource_key,
                    generation_id=generation_id,
                    page_number=page_number,
                    total_pages=total_pages,
                    page_fingerprint=fingerprint,
                    records_json=_json(records),
                    completed_at=utc_now(),
                )
                session.add(row)
            else:
                row.total_pages = total_pages
                row.page_fingerprint = fingerprint
                row.records_json = _json(records)
                row.completed_at = utc_now()
        return {"page_number": page_number, "total_pages": total_pages, "fingerprint": fingerprint}
