"""Exact credential-to-connection bindings; plaintext tokens never persist here."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from modules.coman.models import Base, TimestampMixin
from modules.operational_moats.models import ServiceAccount
from .intelligence_models import Scoped, Versioned, ref

Index('uq_cp_service_account_scope', ServiceAccount.organization_id, ServiceAccount.facility_id, ServiceAccount.id, unique=True)


class CultivationIngressGrant(Scoped, Versioned, TimestampMixin, Base):
    __tablename__ = 'cultivation_ingress_grants'
    __table_args__ = (
        ref('connection_id', 'cultivation_telemetry_connections'),
        ForeignKeyConstraint(['organization_id','facility_id','service_account_id'],
                             ['service_accounts.organization_id','service_accounts.facility_id','service_accounts.id'],
                             name='fk_cp_grant_account_scope', ondelete='RESTRICT'),
        UniqueConstraint('service_account_id', name='uq_cp_grant_account'),
        Index('ix_cp_grant_connection', 'organization_id','facility_id','connection_id'),
    )
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    service_account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_cp_grant_actor', ondelete='RESTRICT'))
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.id', name='fk_cp_grant_revoker', ondelete='RESTRICT'), nullable=True)
