"""Opt-in existing disposable PostgreSQL only; never reads production DB URLs."""
import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from tests.test_cultivation_intelligence_postgres import pg, fixture_rows

TABLE='cultivation_ingress_grants'


def test_push_actual_head_rls_and_composite_binding(pg):
    assert pg.scalar(sa.text('SELECT version_num FROM alembic_version'))=='0091_security_resilience'
    assert pg.scalar(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid='public.cultivation_ingress_grants'::regclass"))
    fks=sa.inspect(pg).get_foreign_keys(TABLE)
    assert any(f['constrained_columns']==['organization_id','facility_id','service_account_id'] and f['referred_table']=='service_accounts' for f in fks)
    assert any(f['constrained_columns']==['organization_id','facility_id','connection_id'] and f['referred_table']=='cultivation_telemetry_connections' for f in fks)
    assert not pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime', 'cultivation_ingress_grants', 'DELETE')"))
    assert pg.scalar(sa.text("SELECT has_column_privilege('doobielogic_render_runtime', 'cultivation_ingress_grants', 'revoked_at', 'UPDATE')"))
    assert not pg.scalar(sa.text("SELECT has_column_privilege('doobielogic_render_runtime', 'cultivation_ingress_grants', 'connection_id', 'UPDATE')"))


@pytest.mark.parametrize('role',['anon','authenticated'])
def test_push_browser_roles_denied(pg,role):
    for sql in ('SELECT * FROM cultivation_ingress_grants LIMIT 1','INSERT INTO cultivation_ingress_grants DEFAULT VALUES'):
        with pg.begin_nested() as savepoint:
            pg.exec_driver_sql('SET LOCAL ROLE '+role)
            with pytest.raises(DBAPIError) as exc:pg.exec_driver_sql(sql)
            assert getattr(exc.value.orig,'sqlstate',None)=='42501'
            savepoint.rollback()


def test_push_downgrade_preserves_connection(pg,fixture_rows):
    from uuid import uuid4
    values={**fixture_rows,'id':str(uuid4())}
    pg.execute(sa.text("INSERT INTO cultivation_telemetry_connections (id,organization_id,facility_id,provider,label,mode,status,created_by,version,created_at,updated_at) VALUES (:id,:org,:facility,'json','Synthetic push','push','configured',:user,1,now(),now())"),values)
    path=Path(__file__).resolve().parents[1]/'migrations/versions/0087_cultivation_push.py'
    spec=importlib.util.spec_from_file_location('push_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.op=Operations(MigrationContext.configure(pg))
    with pytest.raises(RuntimeError,match='preserve it before rollback'):module.downgrade()
    assert pg.scalar(sa.text('SELECT mode FROM cultivation_telemetry_connections WHERE id=:id'),values)=='push'
