"""Add scoped cultivation intelligence relationships without rewriting 0085 evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0086_cultivation_intelligence"
down_revision = "0085_cultivation_telemetry"
branch_labels = None
depends_on = None

TABLES = ('cultivation_recipes', 'cultivation_environment_zones', 'cultivation_recipe_stages', 'cultivation_telemetry_connections', 'cultivation_devices', 'cultivation_recipe_targets', 'cultivation_crop_cycles', 'cultivation_device_mappings', 'cultivation_sensors', 'cultivation_crop_cycle_plants', 'cultivation_crop_cycle_rooms', 'cultivation_operational_events')
ORIGINAL_COLUMNS = ("source_metric", "original_value", "original_unit", "raw_reference")

def _scope_index(name, table, columns):
    # Some historical revisions create individual current ORM tables. Their
    # metadata may already include this additive reference key on a fresh chain.
    existing = next((index for index in sa.inspect(op.get_bind()).get_indexes(table)
                     if index['name'] == name), None)
    if existing is not None:
        if not existing['unique'] or existing['column_names'] != columns:
            raise RuntimeError('Existing cultivation scope index has an incompatible definition.')
        return
    op.create_index(name, table, columns, unique=True)


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '5s'")
    _scope_index("uq_ci_coman_facilities_scope", 'coman_facilities', ['organization_id', 'id'])
    _scope_index("uq_ci_cultivation_plants_scope", 'cultivation_plants', ['organization_id', 'facility_id', 'id'])
    _scope_index("uq_ci_cultivation_plant_groups_scope", 'cultivation_plant_groups', ['organization_id', 'facility_id', 'id'])
    _scope_index("uq_ci_cultivation_harvests_scope", 'cultivation_harvests', ['organization_id', 'facility_id', 'id'])
    _scope_index("uq_ci_integration_configurations_scope", 'integration_configurations', ['organization_id', 'facility_id', 'id'])
    op.create_table('cultivation_recipes',
        sa.Column('name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('description', sa.Text(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('approved_by', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('created_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("status in ('draft','approved')", name='ck_ci_recipe_status'),
        sa.CheckConstraint("(status = 'draft' AND approved_by IS NULL AND approved_at IS NULL) OR (status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)", name='ck_ci_recipe_approval'),
        sa.ForeignKeyConstraint(['created_by'], ['app_users.id'], name='fk_ci_recipe_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['approved_by'], ['app_users.id'], name='fk_ci_recipe_approver', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_recipes_facility', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['facility_id', 'name', 'version'], name='uq_ci_recipe_version'),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_recipes_scope'),
    )
    op.create_table('cultivation_environment_zones',
        sa.Column('room_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('zone_code', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('display_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('active', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_environment_zones_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'room_id'], ['cultivation_rooms.organization_id', 'cultivation_rooms.facility_id', 'cultivation_rooms.id'], name='fk_ci_room_id_rooms', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_environment_zones_scope'),
        sa.UniqueConstraint(*['room_id', 'zone_code'], name='uq_ci_zone_code'),
    )
    op.create_index('uq_ci_zone_room_scope', 'cultivation_environment_zones', ['organization_id', 'facility_id', 'id', 'room_id'], unique=True)
    op.create_table('cultivation_recipe_stages',
        sa.Column('recipe_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('stage_key', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('display_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('sequence', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.CheckConstraint('sequence >= 0', name='ck_ci_stage_sequence'),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'recipe_id'], ['cultivation_recipes.organization_id', 'cultivation_recipes.facility_id', 'cultivation_recipes.id'], name='fk_ci_recipe_id_recipes', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_recipe_stages_facility', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_recipe_stages_scope'),
        sa.UniqueConstraint(*['recipe_id', 'stage_key'], name='uq_ci_stage_key'),
        sa.UniqueConstraint(*['recipe_id', 'sequence'], name='uq_ci_stage_sequence'),
    )
    op.create_table('cultivation_telemetry_connections',
        sa.Column('integration_configuration_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('provider', sa.String(length=80), nullable=False, primary_key=False),
        sa.Column('label', sa.String(length=160), nullable=False, primary_key=False),
        sa.Column('mode', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('created_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint("mode = 'file'", name='ck_ci_connection_mode'),
        sa.CheckConstraint("provider in ('json','csv','growlink')", name='ck_ci_connection_provider'),
        sa.CheckConstraint("status in ('configured','revoked')", name='ck_ci_connection_status'),
        sa.ForeignKeyConstraint(['created_by'], ['app_users.id'], name='fk_ci_connection_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'integration_configuration_id'], ['integration_configurations.organization_id', 'integration_configurations.facility_id', 'integration_configurations.id'], name='fk_ci_integration_configuration_id_integration_configurations', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_telemetry_connections_facility', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['facility_id', 'provider', 'label'], name='uq_ci_connection_label'),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_telemetry_connections_scope'),
    )
    op.create_table('cultivation_devices',
        sa.Column('connection_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('source_device_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('display_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('active', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'connection_id'], ['cultivation_telemetry_connections.organization_id', 'cultivation_telemetry_connections.facility_id', 'cultivation_telemetry_connections.id'], name='fk_ci_connection_id_telemetry_connections', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_devices_facility', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['connection_id', 'source_device_id'], name='uq_ci_device_source'),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_devices_scope'),
    )
    op.create_table('cultivation_recipe_targets',
        sa.Column('stage_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('metric', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('minimum', sa.Float(), nullable=True, primary_key=False),
        sa.Column('maximum', sa.Float(), nullable=True, primary_key=False),
        sa.Column('threshold_seconds', sa.Integer(), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.CheckConstraint('(minimum IS NOT NULL OR maximum IS NOT NULL) AND (minimum IS NULL OR maximum IS NULL OR minimum <= maximum)', name='ck_ci_target_bounds'),
        sa.CheckConstraint('threshold_seconds IS NULL OR (threshold_seconds >= 1 AND threshold_seconds <= 2678400)', name='ck_ci_target_threshold'),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_recipe_targets_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'stage_id'], ['cultivation_recipe_stages.organization_id', 'cultivation_recipe_stages.facility_id', 'cultivation_recipe_stages.id'], name='fk_ci_stage_id_recipe_stages', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_recipe_targets_scope'),
        sa.UniqueConstraint(*['stage_id', 'metric'], name='uq_ci_target_metric'),
    )
    op.create_table('cultivation_crop_cycles',
        sa.Column('cycle_code', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('display_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('genetics_label', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('nursery_group_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('recipe_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('harvest_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('started_on', sa.Date(), nullable=True, primary_key=False),
        sa.Column('estimated_harvest_date', sa.Date(), nullable=True, primary_key=False),
        sa.Column('created_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('version', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint('estimated_harvest_date IS NULL OR started_on IS NULL OR estimated_harvest_date >= started_on', name='ck_ci_cycle_dates'),
        sa.CheckConstraint("status in ('planned','active','harvested','closed','cancelled')", name='ck_ci_cycle_status'),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_crop_cycles_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['created_by'], ['app_users.id'], name='fk_ci_cycle_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'harvest_id'], ['cultivation_harvests.organization_id', 'cultivation_harvests.facility_id', 'cultivation_harvests.id'], name='fk_ci_harvest_id_harvests', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'nursery_group_id'], ['cultivation_plant_groups.organization_id', 'cultivation_plant_groups.facility_id', 'cultivation_plant_groups.id'], name='fk_ci_nursery_group_id_plant_groups', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'recipe_id'], ['cultivation_recipes.organization_id', 'cultivation_recipes.facility_id', 'cultivation_recipes.id'], name='fk_ci_recipe_id_recipes', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_crop_cycles_scope'),
        sa.UniqueConstraint(*['facility_id', 'cycle_code'], name='uq_ci_cycle_code'),
        sa.UniqueConstraint(*['harvest_id'], name='uq_ci_cycle_harvest'),
    )
    op.create_table('cultivation_device_mappings',
        sa.Column('device_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('room_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('zone_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('created_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'device_id'], ['cultivation_devices.organization_id', 'cultivation_devices.facility_id', 'cultivation_devices.id'], name='fk_ci_device_id_devices', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_device_mappings_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['created_by'], ['app_users.id'], name='fk_ci_mapping_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'room_id'], ['cultivation_rooms.organization_id', 'cultivation_rooms.facility_id', 'cultivation_rooms.id'], name='fk_ci_room_id_rooms', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'zone_id', 'room_id'], ['cultivation_environment_zones.organization_id', 'cultivation_environment_zones.facility_id', 'cultivation_environment_zones.id', 'cultivation_environment_zones.room_id'], name='fk_ci_zone_id_environment_zones', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_device_mappings_scope'),
        sa.UniqueConstraint(*['device_id', 'effective_at'], name='uq_ci_mapping_time'),
    )
    op.create_table('cultivation_sensors',
        sa.Column('device_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('source_channel', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('source_metric', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('source_unit', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('metric', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('unit', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'device_id'], ['cultivation_devices.organization_id', 'cultivation_devices.facility_id', 'cultivation_devices.id'], name='fk_ci_device_id_devices', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_sensors_facility', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['device_id', 'source_channel', 'source_metric'], name='uq_ci_sensor_source'),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_sensors_scope'),
    )
    op.create_table('cultivation_crop_cycle_plants',
        sa.Column('cycle_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('plant_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('added_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.CheckConstraint('removed_at IS NULL OR removed_at > added_at', name='ck_ci_member_interval'),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_crop_cycle_plants_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'cycle_id'], ['cultivation_crop_cycles.organization_id', 'cultivation_crop_cycles.facility_id', 'cultivation_crop_cycles.id'], name='fk_ci_cycle_id_crop_cycles', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['added_by'], ['app_users.id'], name='fk_ci_member_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'plant_id'], ['cultivation_plants.organization_id', 'cultivation_plants.facility_id', 'cultivation_plants.id'], name='fk_ci_plant_id_plants', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_crop_cycle_plants_scope'),
    )
    op.create_index('ix_ci_member_time', 'cultivation_crop_cycle_plants', ['facility_id', 'plant_id', 'added_at', 'removed_at'], unique=False)
    op.create_table('cultivation_crop_cycle_rooms',
        sa.Column('cycle_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('room_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('zone_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('stage_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('entered_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('exited_at', sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column('assigned_by', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.CheckConstraint('exited_at IS NULL OR exited_at > entered_at', name='ck_ci_occupancy_interval'),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_crop_cycle_rooms_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'cycle_id'], ['cultivation_crop_cycles.organization_id', 'cultivation_crop_cycles.facility_id', 'cultivation_crop_cycles.id'], name='fk_ci_cycle_id_crop_cycles', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['assigned_by'], ['app_users.id'], name='fk_ci_occupancy_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'room_id'], ['cultivation_rooms.organization_id', 'cultivation_rooms.facility_id', 'cultivation_rooms.id'], name='fk_ci_room_id_rooms', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'stage_id'], ['cultivation_recipe_stages.organization_id', 'cultivation_recipe_stages.facility_id', 'cultivation_recipe_stages.id'], name='fk_ci_stage_id_recipe_stages', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'zone_id', 'room_id'], ['cultivation_environment_zones.organization_id', 'cultivation_environment_zones.facility_id', 'cultivation_environment_zones.id', 'cultivation_environment_zones.room_id'], name='fk_ci_zone_id_environment_zones', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_crop_cycle_rooms_scope'),
    )
    op.create_index('ix_ci_occupancy_time', 'cultivation_crop_cycle_rooms', ['facility_id', 'room_id', 'entered_at', 'exited_at'], unique=False)
    op.create_table('cultivation_operational_events',
        sa.Column('room_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('cycle_id', sa.String(length=36), nullable=True, primary_key=False),
        sa.Column('event_type', sa.String(length=80), nullable=False, primary_key=False),
        sa.Column('title', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('notes', sa.Text(), nullable=False, primary_key=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column('actor', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('id', sa.String(length=36), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('facility_id', sa.String(length=36), nullable=False, primary_key=False),
        sa.CheckConstraint('room_id IS NOT NULL OR cycle_id IS NOT NULL', name='ck_ci_event_context'),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'cycle_id'], ['cultivation_crop_cycles.organization_id', 'cultivation_crop_cycles.facility_id', 'cultivation_crop_cycles.id'], name='fk_ci_cycle_id_crop_cycles', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['actor'], ['app_users.id'], name='fk_ci_event_actor', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id'], ['coman_facilities.organization_id', 'coman_facilities.id'], name='fk_ci_operational_events_facility', ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(['organization_id', 'facility_id', 'room_id'], ['cultivation_rooms.organization_id', 'cultivation_rooms.facility_id', 'cultivation_rooms.id'], name='fk_ci_room_id_rooms', ondelete="RESTRICT"),
        sa.UniqueConstraint(*['organization_id', 'facility_id', 'id'], name='uq_ci_operational_events_scope'),
    )
    op.add_column("cultivation_environment_observations", sa.Column('source_metric', sa.String(120), nullable=True))
    op.add_column("cultivation_environment_observations", sa.Column('original_value', sa.Float(), nullable=True))
    op.add_column("cultivation_environment_observations", sa.Column('original_unit', sa.String(32), nullable=True))
    op.add_column("cultivation_environment_observations", sa.Column('raw_reference', sa.String(255), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
            op.execute(f"""DO $$ DECLARE role_name text; BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                  EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I',role_name);
                END IF;
              END LOOP;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
                REVOKE ALL ON TABLE public.{table} FROM doobielogic_render_runtime;
                GRANT SELECT, INSERT ON TABLE public.{table} TO doobielogic_render_runtime;
                CREATE POLICY ci_server_runtime ON public.{table} TO doobielogic_render_runtime USING (true) WITH CHECK (true);
              END IF;
            END $$;""")


    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='doobielogic_render_runtime') THEN
            GRANT UPDATE ON cultivation_crop_cycles, cultivation_crop_cycle_plants, cultivation_crop_cycle_rooms,
              cultivation_recipes, cultivation_telemetry_connections, cultivation_devices
              TO doobielogic_render_runtime;
          END IF;
        END $$;""")
    op.create_index('uq_ci_member_active', 'cultivation_crop_cycle_plants', ['plant_id'], unique=True,
                    sqlite_where=sa.text('removed_at IS NULL'), postgresql_where=sa.text('removed_at IS NULL'))
    _recipe_guards()


def _recipe_guards():
    # Freeze approved standards even when an internal caller bypasses the service.
    conditions = {
        'cultivation_recipes': "OLD.status = 'approved'",
        'cultivation_recipe_stages': "EXISTS (SELECT 1 FROM cultivation_recipes r WHERE r.id = OLD.recipe_id AND r.status = 'approved')",
        'cultivation_recipe_targets': "EXISTS (SELECT 1 FROM cultivation_recipe_stages s JOIN cultivation_recipes r ON r.id = s.recipe_id WHERE s.id = OLD.stage_id AND r.status = 'approved')",
    }
    for table, condition in conditions.items():
        incoming = condition.replace('OLD.', 'NEW.') if table != 'cultivation_recipes' else 'FALSE'
        parent_column = {'cultivation_recipe_stages': 'recipe_id',
                         'cultivation_recipe_targets': 'stage_id'}.get(table)
        immutable_columns = ('id', 'organization_id', 'facility_id') + ((parent_column,) if parent_column else ())
        changed = ' OR '.join(f'OLD.{column} IS DISTINCT FROM NEW.{column}' for column in immutable_columns)
        parent_guard = (f"IF TG_OP = 'UPDATE' THEN IF {changed} "
                        "THEN RAISE EXCEPTION 'recipe_parent_immutable'; END IF; END IF;")
        if op.get_bind().dialect.name == 'postgresql':
            # Check the tuple returned by the locking read itself. FOR SHARE
            # conflicts with a non-key approval UPDATE; FOR KEY SHARE does not.
            # Old/new parents are locked in ID order, without a status filter
            # that could discard a draft tuple before waiting for approval.
            locks = ''
            if table == 'cultivation_recipe_stages':
                locks = '''IF TG_OP = 'UPDATE' THEN
                  parent_ids := ARRAY[OLD.recipe_id, NEW.recipe_id];
                ELSE parent_ids := ARRAY[OLD.recipe_id]; END IF;'''
            elif table == 'cultivation_recipe_targets':
                locks = '''IF TG_OP = 'UPDATE' THEN
                  SELECT array_agg(s.recipe_id) INTO parent_ids FROM public.cultivation_recipe_stages s
                    WHERE s.id IN (OLD.stage_id, NEW.stage_id);
                ELSE SELECT ARRAY[s.recipe_id] INTO parent_ids FROM public.cultivation_recipe_stages s
                    WHERE s.id = OLD.stage_id; END IF;'''
            check = "IF OLD.status = 'approved' THEN RAISE EXCEPTION 'approved_recipe_immutable'; END IF;"
            if table != 'cultivation_recipes':
                check = '''FOR parent_row IN SELECT r.status FROM public.cultivation_recipes r
                  WHERE r.id = ANY(parent_ids) ORDER BY r.id FOR SHARE LOOP
                  IF parent_row.status = 'approved' THEN
                    RAISE EXCEPTION 'approved_recipe_immutable';
                  END IF;
                END LOOP;'''
            op.execute(f"""CREATE FUNCTION ci_guard_{table}() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE parent_ids text[]; parent_row record;
            BEGIN {parent_guard} {locks} {check}
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
            op.execute(f"CREATE TRIGGER ci_recipe_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ci_guard_{table}()")
        else:
            for operation in ('UPDATE','DELETE'):
                guarded = f'({condition}) OR ({incoming})' if operation == 'UPDATE' else condition
                if operation == 'UPDATE':
                    # Parent relationships are immutable even while draft. A new
                    # version creates new children instead of reparenting evidence.
                    changed = ' OR '.join(f'OLD.{column} IS NOT NEW.{column}' for column in immutable_columns)
                    op.execute(f"CREATE TRIGGER ci_guard_{table}_{operation} BEFORE {operation} ON {table} "
                               f"WHEN ({guarded}) OR ({changed}) BEGIN "
                               f"SELECT CASE WHEN {changed} THEN RAISE(ABORT, 'recipe_parent_immutable') END; "
                               "SELECT RAISE(ABORT, 'approved_recipe_immutable'); END")
                else:
                    op.execute(f"CREATE TRIGGER ci_guard_{table}_{operation} BEFORE {operation} ON {table} WHEN {guarded} BEGIN SELECT RAISE(ABORT, 'approved_recipe_immutable'); END")
    # Inserting a child into an approved version is also an edit.
    for table, condition in list(conditions.items())[1:]:
        condition = condition.replace('OLD.', 'NEW.')
        if op.get_bind().dialect.name == 'postgresql':
            locks = ('parent_ids := ARRAY[NEW.recipe_id];'
                     if table == 'cultivation_recipe_stages' else
                     'SELECT ARRAY[s.recipe_id] INTO parent_ids FROM public.cultivation_recipe_stages s WHERE s.id = NEW.stage_id;')
            op.execute(f"""CREATE FUNCTION ci_insert_guard_{table}() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE parent_ids text[]; parent_row record;
            BEGIN {locks}
            FOR parent_row IN SELECT r.status FROM public.cultivation_recipes r
              WHERE r.id = ANY(parent_ids) ORDER BY r.id FOR SHARE LOOP
              IF parent_row.status = 'approved' THEN RAISE EXCEPTION 'approved_recipe_immutable'; END IF;
            END LOOP;
            RETURN NEW; END $$""")
            op.execute(f"CREATE TRIGGER ci_recipe_insert_guard BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION ci_insert_guard_{table}()")
        else:
            op.execute(f"CREATE TRIGGER ci_guard_{table}_INSERT BEFORE INSERT ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'approved_recipe_immutable'); END")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '5s'")
        op.execute("LOCK TABLE " + ", ".join(TABLES) + ", cultivation_environment_observations IN ACCESS EXCLUSIVE MODE")
    for table in TABLES:
        if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Cultivation intelligence evidence exists; preserve it before rollback.")
    if bind.execute(sa.text("SELECT 1 FROM cultivation_environment_observations WHERE source_metric IS NOT NULL OR original_value IS NOT NULL OR original_unit IS NOT NULL OR raw_reference IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Original telemetry evidence exists; preserve it before rollback.")
    if bind.dialect.name == "postgresql":
        for table in ('cultivation_recipe_targets','cultivation_recipe_stages','cultivation_recipes'):
            op.execute(f"DROP TRIGGER ci_recipe_guard ON {table}")
            op.execute(f"DROP FUNCTION ci_guard_{table}()")
            if table != 'cultivation_recipes':
                op.execute(f"DROP TRIGGER ci_recipe_insert_guard ON {table}")
                op.execute(f"DROP FUNCTION ci_insert_guard_{table}()")
    for column in ORIGINAL_COLUMNS:
        op.drop_column("cultivation_environment_observations", column)
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_index("uq_ci_integration_configurations_scope", table_name='integration_configurations')
    op.drop_index("uq_ci_cultivation_harvests_scope", table_name='cultivation_harvests')
    op.drop_index("uq_ci_cultivation_plant_groups_scope", table_name='cultivation_plant_groups')
    op.drop_index("uq_ci_cultivation_plants_scope", table_name='cultivation_plants')
    op.drop_index("uq_ci_coman_facilities_scope", table_name='coman_facilities')
