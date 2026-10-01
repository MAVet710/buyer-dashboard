"""Explicit disposable PostgreSQL verification, never the production database."""
import json
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from tests.test_cultivation_intelligence_postgres import pg,fixture_rows
from modules.alpha_mode.models import AlphaOperatingMode
from modules.integrations.models import IntegrationConfiguration
from modules.cultivation.intelligence_models import TelemetryConnection
from modules.coman.models import new_id


def test_actual_0089_constraints_and_runtime_writes(pg,fixture_rows):
    x=fixture_rows
    assert pg.scalar(sa.text('SELECT version_num FROM alembic_version'))=='0091_security_resilience'
    with Session(bind=pg,join_transaction_mode='create_savepoint') as s,s.begin():
        mode=AlphaOperatingMode(organization_id=x['org'],facility_id=x['facility'],mode='metrc_production',updated_by=x['user'])
        config=IntegrationConfiguration(organization_id=x['org'],facility_id=x['facility'],scope_type='facility',scope_key=new_id(),
            provider='cultivation_network',configuration_json='{}',encrypted_secret='',secret_hint='',status='configured',updated_by=x['user'])
        s.add_all([mode,config]);s.flush();mode_id,config_id=mode.id,config.id
        row=TelemetryConnection(organization_id=x['org'],facility_id=x['facility'],provider='json',mode='network',
            label='PG fixture '+new_id(),integration_configuration_id=config.id,created_by=x['user'])
        s.add(row);s.flush();connection_id=row.id
    pg.exec_driver_sql('SET LOCAL ROLE doobielogic_render_runtime')
    pg.execute(sa.text("UPDATE alpha_operating_modes SET mode='doobielogic_sandbox' WHERE id=:id"),{'id':mode_id})
    pg.execute(sa.text("UPDATE integration_configurations SET configuration_json=:value WHERE id=:id"),{'id':config_id,'value':json.dumps({'enabled':False})})
    pg.execute(sa.text('UPDATE cultivation_telemetry_connections SET version=version+1 WHERE id=:id'),{'id':connection_id})
    assert pg.scalar(sa.text('SELECT version FROM cultivation_telemetry_connections WHERE id=:id'),{'id':connection_id})==2
    assert pg.scalar(sa.text('SELECT pg_try_advisory_xact_lock(823781)')) is True
    pg.exec_driver_sql('RESET ROLE')


@pytest.mark.parametrize('role',['anon','authenticated'])
def test_network_and_credential_tables_are_not_browser_readable(pg,role):
    for table in ('integration_configurations','cultivation_telemetry_connections'):
        with pg.begin_nested() as savepoint:
            pg.exec_driver_sql('SET LOCAL ROLE '+role)
            with pytest.raises(DBAPIError) as failure:
                pg.exec_driver_sql('SELECT * FROM '+table+' LIMIT 1')
            assert failure.value.orig.sqlstate=='42501'
            savepoint.rollback()


def test_fresh_baseline_grants_do_not_allow_scope_rebinding_or_delete(pg):
    for table in ('alpha_operating_modes','integration_configurations'):
        assert not pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime',:table,'DELETE')"),{'table':table})
        for column in ('organization_id','facility_id','id'):
            assert not pg.scalar(sa.text("SELECT has_column_privilege('doobielogic_render_runtime',:table,:column,'UPDATE')"),{'table':table,'column':column})
