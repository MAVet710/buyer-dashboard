"""Disposable PostgreSQL verification for security resilience state and grants."""
import json
import sqlalchemy as sa
import pytest
from sqlalchemy.exc import DBAPIError

from tests.test_cultivation_intelligence_postgres import pg


def test_security_resilience_head_schema_and_runtime_grants(pg):
    assert pg.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0091_security_resilience"
    inspector = sa.inspect(pg)
    incident_columns = {row["name"] for row in inspector.get_columns("security_incidents")}
    monitor_columns = {row["name"] for row in inspector.get_columns("security_monitor_state")}
    event_columns = {row["name"]: row for row in inspector.get_columns("security_events")}
    assert getattr(event_columns["actor_id"]["type"], "length", None) == 64
    assert {"recovered_at", "recovery_json"} <= incident_columns
    assert {"last_error_category", "last_error_at", "clean_cycles"} <= monitor_columns
    assert "security_source_state" in inspector.get_table_names()
    assert pg.scalar(sa.text(
        "SELECT relrowsecurity FROM pg_class WHERE oid='public.security_source_state'::regclass"
    )) is True

    pg.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
    pg.execute(sa.text("""
        INSERT INTO security_source_state
          (id,checked_at,status,cursor,failures,last_error_category,last_event_at,detail_json)
        VALUES ('test:source',1,'observing','1',0,'',0,:detail)
    """), {"detail": json.dumps({"security_events": True})})
    pg.execute(sa.text("""
        UPDATE security_source_state
        SET checked_at=2,status='connected_empty',cursor='2',last_event_at=2
        WHERE id='test:source'
    """))
    assert pg.scalar(sa.text(
        "SELECT status FROM security_source_state WHERE id='test:source'"
    )) == "connected_empty"
    pg.exec_driver_sql("RESET ROLE")


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_access_security_source_state(pg, role):
    for statement in (
        "SELECT * FROM security_source_state LIMIT 1",
        "INSERT INTO security_source_state (id,checked_at,status,cursor,failures,last_error_category,last_event_at,detail_json) "
        "VALUES ('x',1,'observing','',0,'',0,'{}')",
    ):
        with pg.begin_nested() as savepoint:
            pg.exec_driver_sql("SET LOCAL ROLE " + role)
            with pytest.raises(DBAPIError) as failure:
                pg.exec_driver_sql(statement)
            assert failure.value.orig.sqlstate == "42501"
            savepoint.rollback()


def test_runtime_cannot_delete_new_security_source_state(pg):
    assert not pg.scalar(sa.text(
        "SELECT has_table_privilege('doobielogic_render_runtime','security_source_state','DELETE')"
    ))
