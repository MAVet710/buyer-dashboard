"""Migration rollback only on empty, disposable test storage."""
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, MetaData, Table, select, func

PATH=Path(__file__).resolve().parents[1]/"migrations/versions/0079_security_observation.py"
TABLES={"security_events","security_incidents","security_monitor_state"}


def migration():
    spec=importlib.util.spec_from_file_location("security_migration_test",PATH)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_unused_security_tables_can_roll_back_and_upgrade_again():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        revision=migration(); revision.upgrade()
        assert TABLES <= set(inspect(connection).get_table_names())
        revision.downgrade()
        assert not TABLES.intersection(inspect(connection).get_table_names())
        revision.upgrade()
        assert TABLES <= set(inspect(connection).get_table_names())
    engine.dispose()


@pytest.mark.parametrize("name",sorted(TABLES))
def test_populated_security_table_prevents_all_destructive_rollback(name):
    engine=create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        revision=migration(); revision.upgrade()
        table=Table(name,MetaData(),autoload_with=connection)
        values={"id":"retained-test-record"}
        if name=="security_events": values.update(occurred_at=1000,kind="login_failure")
        elif name=="security_incidents": values.update(fingerprint="test-fingerprint",rule="login_failures",
            severity="high",title="Synthetic",group_key="synthetic",first_seen=1000,last_seen=1000,occurrences=8)
        else: values.update(checked_at=1000,status="observing")
        connection.execute(table.insert().values(**values))
        with pytest.raises(RuntimeError,match="Security records exist"):
            revision.downgrade()
        assert TABLES <= set(inspect(connection).get_table_names())
        assert connection.scalar(select(func.count()).select_from(table))==1
    engine.dispose()
