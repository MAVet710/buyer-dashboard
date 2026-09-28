"""Actual 0088 constraints and grants, opt-in disposable PostgreSQL only."""
import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from tests.test_cultivation_intelligence_postgres import pg, fixture_rows
from modules.cultivation.radio.models import RadioBinding
from modules.cultivation.intelligence_models import TelemetryConnection, CultivationDevice

TABLE = 'cultivation_radio_bindings'


def test_radio_head_and_least_privilege(pg):
    assert pg.scalar(sa.text('SELECT version_num FROM alembic_version')) == '0090_security_guard'
    assert pg.scalar(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid='public.cultivation_radio_bindings'::regclass"))
    assert pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime', :table, 'SELECT,INSERT')"), {'table':TABLE})
    for column in ('active', 'enabled_at', 'version'):
        assert pg.scalar(sa.text("SELECT has_column_privilege('doobielogic_render_runtime', :table, :column, 'UPDATE')"), {'table':TABLE,'column':column})
    for column in ('source_address', 'connection_id', 'device_id', 'organization_id'):
        assert not pg.scalar(sa.text("SELECT has_column_privilege('doobielogic_render_runtime', :table, :column, 'UPDATE')"), {'table':TABLE,'column':column})
    assert not pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime', :table, 'DELETE')"), {'table':TABLE})
    fks = sa.inspect(pg).get_foreign_keys(TABLE)
    assert any(row['constrained_columns']==['organization_id','facility_id','device_id','connection_id'] for row in fks)


@pytest.mark.parametrize('role', ['anon','authenticated'])
def test_browser_roles_cannot_read_or_insert_radio_bindings(pg, role):
    for statement in ('SELECT * FROM cultivation_radio_bindings LIMIT 1',
                      'INSERT INTO cultivation_radio_bindings DEFAULT VALUES'):
        with pg.begin_nested() as savepoint:
            pg.exec_driver_sql('SET LOCAL ROLE '+role)
            with pytest.raises(DBAPIError) as failure:
                pg.exec_driver_sql(statement)
            assert failure.value.orig.sqlstate == '42501'
            savepoint.rollback()


def test_runtime_link_scoped_identity_and_downgrade_refusal(pg, fixture_rows):
    x = fixture_rows
    with Session(bind=pg, join_transaction_mode='create_savepoint') as session, session.begin():
        connection = TelemetryConnection(id=str(uuid4()), organization_id=x['org'], facility_id=x['facility'],
            provider='json', mode='file', label='Radio test '+str(uuid4()), created_by=x['user'])
        session.add(connection); session.flush()
        device = CultivationDevice(id=str(uuid4()), organization_id=x['org'], facility_id=x['facility'],
            connection_id=connection.id, source_device_id='radio:test', display_name='Synthetic')
        session.add(device); session.flush()
        values = dict(id=str(uuid4()), organization_id=x['org'], facility_id=x['facility'],
            receiver_id='ble', source_address='AABBCCDDEEFF', profile_id='bthome_v2',
            connection_id=connection.id, device_id=device.id, created_by=x['user'],
            enabled_at=sa.func.now(), authorized_by=x['user'], active=True, version=1)
    pg.exec_driver_sql('SET LOCAL ROLE doobielogic_render_runtime')
    pg.execute(sa.insert(RadioBinding).values(**values))
    with pg.begin_nested() as savepoint:
        with pytest.raises(DBAPIError) as failure:
            pg.execute(sa.insert(RadioBinding).values(**dict(values, id=str(uuid4()))))
        assert failure.value.orig.sqlstate == '23505'
        savepoint.rollback()
    # Use the test owner to test FK integrity separately from runtime ACL denial.
    pg.exec_driver_sql('RESET ROLE')
    with pg.begin_nested() as savepoint:
        with pytest.raises(DBAPIError) as failure:
            pg.execute(sa.update(RadioBinding).where(RadioBinding.id==values['id']).values(organization_id=x['other_org']))
        assert failure.value.orig.sqlstate == '23503'
        savepoint.rollback()
    pg.exec_driver_sql('SET LOCAL ROLE doobielogic_render_runtime')
    pg.execute(sa.update(RadioBinding).where(RadioBinding.id==values['id']).values(active=False, version=2))
    assert not pg.scalar(sa.select(RadioBinding.active).where(RadioBinding.id==values['id']))
    pg.exec_driver_sql('RESET ROLE')
    path=Path(__file__).resolve().parents[1]/'migrations/versions/0088_cultivation_radio.py'
    spec=importlib.util.spec_from_file_location('radio_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.op=Operations(MigrationContext.configure(pg))
    with pytest.raises(RuntimeError,match='Radio approval evidence exists'):
        module.downgrade()
    assert pg.scalar(sa.select(RadioBinding.version).where(RadioBinding.id==values['id']))==2
