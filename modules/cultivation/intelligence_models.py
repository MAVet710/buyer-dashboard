"""Scoped relationship records. Raw sensor evidence belongs to the local edge store."""
from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, declared_attr
from modules.coman.models import Base, Facility, TimestampMixin, new_id
from modules.operational_moats.models import CultivationHarvest
from modules.integrations.models import IntegrationConfiguration
from .models import CultivationPlant, CultivationRoom
from .batch_models import CultivationPlantGroup

# Composite reference keys are additive indexes, also installed by migration 0086.
for model in (Facility, CultivationPlant, CultivationPlantGroup, CultivationHarvest, IntegrationConfiguration):
    columns = [model.organization_id, model.id] if model is Facility else [model.organization_id, model.facility_id, model.id]
    Index('uq_ci_' + model.__tablename__ + '_scope', *columns, unique=True)


def ref(column, table, *, extra=()):
    local = ['organization_id', 'facility_id', column] + [x[0] for x in extra]
    remote = [table + '.organization_id', table + '.facility_id', table + '.id'] + [table + '.' + x[1] for x in extra]
    return ForeignKeyConstraint(local, remote, name='fk_ci_' + column + '_' + table.removeprefix('cultivation_'), ondelete='RESTRICT')


class Scoped:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    facility_id: Mapped[str] = mapped_column(String(36), nullable=False)

    @declared_attr.directive
    def __table_args__(cls):
        return ()


class Versioned:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EnvironmentalZone(Scoped, Base):
    __tablename__ = 'cultivation_environment_zones'
    __table_args__ = (ref('room_id', 'cultivation_rooms'), UniqueConstraint('room_id', 'zone_code', name='uq_ci_zone_code'))
    room_id: Mapped[str] = mapped_column(String(36))
    zone_code: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(255), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TelemetryConnection(Scoped, Versioned, TimestampMixin, Base):
    __tablename__ = 'cultivation_telemetry_connections'
    __table_args__ = (UniqueConstraint('facility_id', 'provider', 'label', name='uq_ci_connection_label'),
                      CheckConstraint("mode = 'file' OR (mode = 'push' AND provider = 'json') OR (mode = 'network' AND provider = 'json')", name='ck_ci_connection_mode'),
                      CheckConstraint("provider in ('json','csv','growlink')", name='ck_ci_connection_provider'),
                      CheckConstraint("status in ('configured','revoked')", name='ck_ci_connection_status'),
                      CheckConstraint('expected_interval_seconds IS NULL OR expected_interval_seconds BETWEEN 1 AND 2678400', name='ck_cp_expected_interval'),
                      CheckConstraint('stale_after_seconds IS NULL OR stale_after_seconds BETWEEN 1 AND 2678400', name='ck_cp_stale_after'),
                      ref('integration_configuration_id', 'integration_configurations'))
    integration_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(32), default='file')
    status: Mapped[str] = mapped_column(String(32), default='configured')
    expected_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stale_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_ci_connection_actor', ondelete='RESTRICT'))


class CultivationDevice(Scoped, Versioned, Base):
    __tablename__ = 'cultivation_devices'
    __table_args__ = (ref('connection_id', 'cultivation_telemetry_connections'), UniqueConstraint('connection_id', 'source_device_id', name='uq_ci_device_source'))
    connection_id: Mapped[str] = mapped_column(String(36))
    source_device_id: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(255), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DeviceMapping(Scoped, Base):
    __tablename__ = 'cultivation_device_mappings'
    __table_args__ = (ref('device_id', 'cultivation_devices'), ref('room_id', 'cultivation_rooms'),
                      ref('zone_id', 'cultivation_environment_zones', extra=(('room_id','room_id'),)),
                      UniqueConstraint('device_id', 'effective_at', name='uq_ci_mapping_time'))
    device_id: Mapped[str] = mapped_column(String(36))
    room_id: Mapped[str] = mapped_column(String(36))
    zone_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_ci_mapping_actor', ondelete='RESTRICT'))


class CultivationSensor(Scoped, Base):
    __tablename__ = 'cultivation_sensors'
    __table_args__ = (ref('device_id', 'cultivation_devices'), UniqueConstraint('device_id', 'source_channel', 'source_metric', name='uq_ci_sensor_source'))
    device_id: Mapped[str] = mapped_column(String(36))
    source_channel: Mapped[str] = mapped_column(String(120))
    source_metric: Mapped[str] = mapped_column(String(120))
    source_unit: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))


class CultivationRecipe(Scoped, TimestampMixin, Base):
    __tablename__ = 'cultivation_recipes'
    __table_args__ = (UniqueConstraint('facility_id', 'name', 'version', name='uq_ci_recipe_version'),
                      CheckConstraint("(status = 'draft' AND approved_by IS NULL AND approved_at IS NULL) OR (status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)", name='ck_ci_recipe_approval'),
                      CheckConstraint("status in ('draft','approved')", name='ck_ci_recipe_status'))
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(24), default='draft')
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.id', name='fk_ci_recipe_approver', ondelete='RESTRICT'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_ci_recipe_actor', ondelete='RESTRICT'))


class CultivationRecipeStage(Scoped, Base):
    __tablename__ = 'cultivation_recipe_stages'
    __table_args__ = (ref('recipe_id', 'cultivation_recipes'), UniqueConstraint('recipe_id','stage_key',name='uq_ci_stage_key'), UniqueConstraint('recipe_id','sequence',name='uq_ci_stage_sequence'), CheckConstraint('sequence >= 0',name='ck_ci_stage_sequence'))
    recipe_id: Mapped[str] = mapped_column(String(36))
    stage_key: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(255))
    sequence: Mapped[int] = mapped_column(Integer)


class CultivationRecipeTarget(Scoped, Base):
    __tablename__ = 'cultivation_recipe_targets'
    __table_args__ = (ref('stage_id', 'cultivation_recipe_stages'), UniqueConstraint('stage_id','metric',name='uq_ci_target_metric'), CheckConstraint('(minimum IS NOT NULL OR maximum IS NOT NULL) AND (minimum IS NULL OR maximum IS NULL OR minimum <= maximum)',name='ck_ci_target_bounds'), CheckConstraint('threshold_seconds IS NULL OR (threshold_seconds >= 1 AND threshold_seconds <= 2678400)',name='ck_ci_target_threshold'))
    stage_id: Mapped[str] = mapped_column(String(36))
    metric: Mapped[str] = mapped_column(String(64))
    minimum: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit: Mapped[str] = mapped_column(String(32))


class CropCycle(Scoped, Versioned, TimestampMixin, Base):
    __tablename__ = 'cultivation_crop_cycles'
    __table_args__ = (ref('nursery_group_id', 'cultivation_plant_groups'), ref('recipe_id','cultivation_recipes'), ref('harvest_id','cultivation_harvests'),
                      UniqueConstraint('facility_id','cycle_code',name='uq_ci_cycle_code'), UniqueConstraint('harvest_id',name='uq_ci_cycle_harvest'),
                      CheckConstraint("status in ('planned','active','harvested','closed','cancelled')",name='ck_ci_cycle_status'),
                      CheckConstraint('estimated_harvest_date IS NULL OR started_on IS NULL OR estimated_harvest_date >= started_on',name='ck_ci_cycle_dates'))
    cycle_code: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(255))
    genetics_label: Mapped[str] = mapped_column(String(255), default='')
    nursery_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recipe_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    harvest_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default='planned')
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_ci_cycle_actor', ondelete='RESTRICT'))


class CropCyclePlant(Scoped, Base):
    __tablename__ = 'cultivation_crop_cycle_plants'
    __table_args__ = (ref('cycle_id','cultivation_crop_cycles'), ref('plant_id','cultivation_plants'),
                      CheckConstraint('removed_at IS NULL OR removed_at > added_at',name='ck_ci_member_interval'),
                      Index('ix_ci_member_time','facility_id','plant_id','added_at','removed_at'))
    cycle_id: Mapped[str] = mapped_column(String(36))
    plant_id: Mapped[str] = mapped_column(String(36))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_ci_member_actor', ondelete='RESTRICT'))


class CropCycleRoom(Scoped, Base):
    __tablename__ = 'cultivation_crop_cycle_rooms'
    __table_args__ = (ref('cycle_id','cultivation_crop_cycles'), ref('room_id','cultivation_rooms'),
                      ref('zone_id','cultivation_environment_zones',extra=(('room_id','room_id'),)), ref('stage_id','cultivation_recipe_stages'),
                      CheckConstraint('exited_at IS NULL OR exited_at > entered_at',name='ck_ci_occupancy_interval'),
                      Index('ix_ci_occupancy_time','facility_id','room_id','entered_at','exited_at'))
    cycle_id: Mapped[str] = mapped_column(String(36))
    room_id: Mapped[str] = mapped_column(String(36))
    zone_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[str] = mapped_column(ForeignKey('app_users.id', name='fk_ci_occupancy_actor', ondelete='RESTRICT'))


class CultivationOperationalEvent(Scoped, Base):
    __tablename__ = 'cultivation_operational_events'
    __table_args__ = (ref('room_id','cultivation_rooms'),ref('cycle_id','cultivation_crop_cycles'),CheckConstraint('room_id IS NOT NULL OR cycle_id IS NOT NULL',name='ck_ci_event_context'))
    room_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default='')
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(ForeignKey('app_users.id',name='fk_ci_event_actor',ondelete='RESTRICT'))


DOMAIN_MODELS = (EnvironmentalZone, TelemetryConnection, CultivationDevice, DeviceMapping, CultivationSensor, CultivationRecipe, CultivationRecipeStage, CultivationRecipeTarget, CropCycle, CropCyclePlant, CropCycleRoom, CultivationOperationalEvent)
for model in DOMAIN_MODELS:
    table = model.__table__
    table.append_constraint(UniqueConstraint('organization_id','facility_id','id',name='uq_ci_' + table.name.removeprefix('cultivation_') + '_scope'))
    table.append_constraint(ForeignKeyConstraint(['organization_id','facility_id'], ['coman_facilities.organization_id','coman_facilities.id'],name='fk_ci_' + table.name.removeprefix('cultivation_') + '_facility',ondelete='RESTRICT'))
Index('uq_ci_zone_room_scope', EnvironmentalZone.organization_id, EnvironmentalZone.facility_id, EnvironmentalZone.id, EnvironmentalZone.room_id, unique=True)

# A plant can have only one open membership, including under concurrent writers.
Index('uq_ci_member_active', CropCyclePlant.plant_id, unique=True,
      sqlite_where=text('removed_at IS NULL'), postgresql_where=text('removed_at IS NULL'))
