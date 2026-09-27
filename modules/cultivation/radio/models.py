"""Only explicitly approved radio bindings persist. Discovery is ephemeral."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from modules.coman.models import Base, new_id, utc_now
from ..intelligence_models import CultivationDevice

Index('uq_radio_device_connection_scope', CultivationDevice.organization_id, CultivationDevice.facility_id,
      CultivationDevice.id, CultivationDevice.connection_id, unique=True)

class RadioBinding(Base):
    __tablename__ = 'cultivation_radio_bindings'
    __table_args__ = (
        UniqueConstraint('organization_id','facility_id','receiver_id','source_address', name='uq_radio_source'),
        UniqueConstraint('connection_id', name='uq_radio_connection'),
        UniqueConstraint('organization_id','facility_id','id', name='uq_radio_binding_scope'),
        ForeignKeyConstraint(['organization_id','facility_id'], ['coman_facilities.organization_id','coman_facilities.id'], name='fk_radio_facility', ondelete='RESTRICT'),
        ForeignKeyConstraint(['organization_id','facility_id','connection_id'], ['cultivation_telemetry_connections.organization_id','cultivation_telemetry_connections.facility_id','cultivation_telemetry_connections.id'], name='fk_radio_connection', ondelete='RESTRICT'),
        ForeignKeyConstraint(['organization_id','facility_id','device_id','connection_id'], ['cultivation_devices.organization_id','cultivation_devices.facility_id','cultivation_devices.id','cultivation_devices.connection_id'], name='fk_radio_device_connection', ondelete='RESTRICT'),
        CheckConstraint("profile_id IN ('bthome_v2','ambient_wh31')", name='ck_radio_profile'),
        CheckConstraint('version >= 1', name='ck_radio_version'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(36), nullable=False)
    receiver_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_address: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_radio_actor', ondelete='RESTRICT'), nullable=False)
    authorized_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_radio_authorizer', ondelete='RESTRICT'), nullable=False, default=lambda context: context.get_current_parameters()['created_by'])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    enabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
