from io import StringIO
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.schema import CreateTable
from migrations.version_table import REVISION_CAPACITY, widen_existing_version_table


def test_postgres_version_table_preserves_full_historical_revision_ids():
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": StringIO()})
    table = context.impl.version_table_impl(version_table="alembic_version", version_table_schema=None, version_table_pk=True)
    revisions = list(ScriptDirectory.from_config(Config("alembic.ini")).walk_revisions())
    assert len("0011_commercial_order_fulfillment") > 32
    assert max(len(row.revision) for row in revisions) <= table.c.version_num.type.length == REVISION_CAPACITY
    assert list(table.primary_key.columns.keys()) == ["version_num"]
    assert "VARCHAR(128)" in str(CreateTable(table).compile(dialect=context.dialect))


def test_bookkeeping_capacity_does_not_touch_other_dialects():
    class Connection:
        class dialect:
            name = "sqlite"
        def exec_driver_sql(self, *args):
            raise AssertionError("Other dialects must be unchanged")
    widen_existing_version_table(Connection())
