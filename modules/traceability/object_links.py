"""Durable local-to-provider identity links for regulated objects.

This table is intentionally provider-neutral. A DoobieLogic object is never
matched to Metrc (or another state system) by a mutable display name once a
provider identity exists. Links are created/updated only by controlled services
that have fresh provider evidence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Engine, ForeignKey, Index, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from modules.coman.models import Base, TimestampMixin, new_id, utc_now
from .models import TRACEABILITY_PROVIDERS


LINK_STATUSES = ("verified", "stale", "reconciliation_required")


class TraceabilityObjectLink(TimestampMixin, Base):
    """Exact identity bridge between one local object and one provider object."""

    __tablename__ = "traceability_object_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "entity_type",
            "entity_id",
            name="uq_traceability_object_link_local",
        ),
        UniqueConstraint(
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "provider_resource",
            "provider_id",
            name="uq_traceability_object_link_provider",
        ),
        CheckConstraint("provider in ('metrc','biotrack','other')", name="ck_traceability_object_link_provider"),
        CheckConstraint("status in ('verified','stale','reconciliation_required')", name="ck_traceability_object_link_status"),
        Index(
            "ix_traceability_object_link_local_lookup",
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_traceability_object_link_provider_lookup",
            "organization_id",
            "facility_id",
            "provider",
            "environment",
            "provider_resource",
            "provider_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        ForeignKey("coman_facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    license_number: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_resource: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="verified")
    source_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("traceability_transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    mismatch_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")


class TraceabilityObjectLinkRepository:
    """Tenant-safe identity registry with fail-closed rebinding semantics."""

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _facility_ok(session, organization_id: str, facility_id: str) -> bool:
        from modules.coman.models import Facility

        facility = session.get(Facility, facility_id)
        return bool(facility and facility.organization_id == organization_id)

    def upsert_verified(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        jurisdiction: str,
        environment: str,
        license_number: str,
        entity_type: str,
        entity_id: str,
        provider_resource: str,
        provider_id: str,
        provider_label: str = "",
        source_transaction_id: str | None = None,
    ) -> TraceabilityObjectLink:
        provider_name = self._clean(provider).casefold()
        env = self._clean(environment).casefold()
        local_type = self._clean(entity_type).casefold()
        local_id = self._clean(entity_id)
        resource = self._clean(provider_resource).casefold()
        external_id = self._clean(provider_id)
        license_no = self._clean(license_number)
        if provider_name not in TRACEABILITY_PROVIDERS:
            raise ValueError("Unsupported traceability provider.")
        if env not in {"sandbox", "production"}:
            raise ValueError("Regulatory object links require an exact provider environment.")
        if not all((local_type, local_id, resource, external_id, license_no)):
            raise ValueError("Local identity, provider resource/ID, and license are required for a regulatory object link.")

        try:
            with self.sessions.begin() as session:
                if not self._facility_ok(session, organization_id, facility_id):
                    raise ValueError("Facility does not belong to the organization.")
                local = session.scalar(
                    select(TraceabilityObjectLink).where(
                        TraceabilityObjectLink.organization_id == organization_id,
                        TraceabilityObjectLink.facility_id == facility_id,
                        TraceabilityObjectLink.provider == provider_name,
                        TraceabilityObjectLink.environment == env,
                        TraceabilityObjectLink.entity_type == local_type,
                        TraceabilityObjectLink.entity_id == local_id,
                    ).with_for_update()
                )
                provider_link = session.scalar(
                    select(TraceabilityObjectLink).where(
                        TraceabilityObjectLink.organization_id == organization_id,
                        TraceabilityObjectLink.facility_id == facility_id,
                        TraceabilityObjectLink.provider == provider_name,
                        TraceabilityObjectLink.environment == env,
                        TraceabilityObjectLink.provider_resource == resource,
                        TraceabilityObjectLink.provider_id == external_id,
                    ).with_for_update()
                )
                if provider_link is not None and (
                    provider_link.entity_type != local_type or provider_link.entity_id != local_id
                ):
                    raise ValueError("That provider object is already linked to a different DoobieLogic object.")
                if local is not None and (
                    local.provider_resource != resource or local.provider_id != external_id
                ):
                    raise ValueError(
                        "This DoobieLogic object is already linked to a different provider identity. Reconcile the existing link instead of rebinding by name."
                    )

                now = utc_now()
                row = local or provider_link
                if row is None:
                    row = TraceabilityObjectLink(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        provider=provider_name,
                        jurisdiction=self._clean(jurisdiction).upper(),
                        environment=env,
                        license_number=license_no,
                        entity_type=local_type,
                        entity_id=local_id,
                        provider_resource=resource,
                        provider_id=external_id,
                        provider_label=self._clean(provider_label),
                        status="verified",
                        source_transaction_id=self._clean(source_transaction_id) or None,
                        verified_at=now,
                        last_seen_at=now,
                    )
                    session.add(row)
                else:
                    if row.license_number != license_no:
                        raise ValueError("Provider identity belongs to a different facility license and cannot be rebound.")
                    row.jurisdiction = self._clean(jurisdiction).upper()
                    row.provider_label = self._clean(provider_label) or row.provider_label
                    row.status = "verified"
                    row.mismatch_reason = ""
                    row.source_transaction_id = self._clean(source_transaction_id) or row.source_transaction_id
                    row.verified_at = now
                    row.last_seen_at = now
                session.flush()
                return row
        except IntegrityError:
            # Unique constraints are the final arbiter for simultaneous link
            # establishment. Re-read exact local identity and only accept the
            # race winner when it is the same provider identity.
            existing = self.get_local(
                organization_id=organization_id,
                facility_id=facility_id,
                provider=provider_name,
                environment=env,
                entity_type=local_type,
                entity_id=local_id,
            )
            if existing and existing.provider_resource == resource and existing.provider_id == external_id:
                return existing
            raise

    def get_local(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        environment: str,
        entity_type: str,
        entity_id: str,
    ) -> TraceabilityObjectLink | None:
        with self.sessions() as session:
            return session.scalar(
                select(TraceabilityObjectLink).where(
                    TraceabilityObjectLink.organization_id == organization_id,
                    TraceabilityObjectLink.facility_id == facility_id,
                    TraceabilityObjectLink.provider == self._clean(provider).casefold(),
                    TraceabilityObjectLink.environment == self._clean(environment).casefold(),
                    TraceabilityObjectLink.entity_type == self._clean(entity_type).casefold(),
                    TraceabilityObjectLink.entity_id == self._clean(entity_id),
                )
            )

    def get_provider(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        environment: str,
        provider_resource: str,
        provider_id: str,
    ) -> TraceabilityObjectLink | None:
        with self.sessions() as session:
            return session.scalar(
                select(TraceabilityObjectLink).where(
                    TraceabilityObjectLink.organization_id == organization_id,
                    TraceabilityObjectLink.facility_id == facility_id,
                    TraceabilityObjectLink.provider == self._clean(provider).casefold(),
                    TraceabilityObjectLink.environment == self._clean(environment).casefold(),
                    TraceabilityObjectLink.provider_resource == self._clean(provider_resource).casefold(),
                    TraceabilityObjectLink.provider_id == self._clean(provider_id),
                )
            )

    def mark_reconciliation_required(
        self,
        *,
        organization_id: str,
        facility_id: str,
        link_id: str,
        reason: str,
    ) -> TraceabilityObjectLink:
        with self.sessions.begin() as session:
            row = session.get(TraceabilityObjectLink, link_id)
            if not row or row.organization_id != organization_id or row.facility_id != facility_id:
                raise ValueError("Regulatory object link was not found in the active facility.")
            row.status = "reconciliation_required"
            row.mismatch_reason = self._clean(reason) or "Provider and local identity require review."
            row.last_seen_at = utc_now()
            session.flush()
            return row

    def list_facility(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str = "metrc",
        environment: str = "",
        status: str = "",
        limit: int = 1000,
    ) -> list[TraceabilityObjectLink]:
        with self.sessions() as session:
            statement = select(TraceabilityObjectLink).where(
                TraceabilityObjectLink.organization_id == organization_id,
                TraceabilityObjectLink.facility_id == facility_id,
                TraceabilityObjectLink.provider == self._clean(provider).casefold(),
            )
            if environment:
                statement = statement.where(TraceabilityObjectLink.environment == self._clean(environment).casefold())
            if status:
                normalized_status = self._clean(status).casefold()
                if normalized_status not in LINK_STATUSES:
                    raise ValueError("Unsupported regulatory object link status.")
                statement = statement.where(TraceabilityObjectLink.status == normalized_status)
            return list(
                session.scalars(
                    statement.order_by(TraceabilityObjectLink.entity_type, TraceabilityObjectLink.entity_id).limit(
                        max(1, min(int(limit or 1000), 5000))
                    )
                )
            )

    @staticmethod
    def payload(row: TraceabilityObjectLink) -> dict[str, object]:
        return {
            "id": row.id,
            "provider": row.provider,
            "jurisdiction": row.jurisdiction,
            "environment": row.environment,
            "license_number": row.license_number,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "provider_resource": row.provider_resource,
            "provider_id": row.provider_id,
            "provider_label": row.provider_label,
            "status": row.status,
            "source_transaction_id": row.source_transaction_id,
            "verified_at": row.verified_at.isoformat() if row.verified_at else None,
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "mismatch_reason": row.mismatch_reason,
        }
