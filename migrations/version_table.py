"""PostgreSQL migration bookkeeping capacity; never runs at application startup.

Uses Alembic's documented dialect version_table_impl hook (Alembic >=1.14).
Existing revision identities and the normal Alembic history are not rewritten.
"""
from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import String, inspect

REVISION_CAPACITY = 128


class DoobieLogicPostgresqlImpl(PostgresqlImpl):
    __dialect__ = "postgresql"

    def version_table_impl(self, **kwargs):
        table = super().version_table_impl(**kwargs)
        table.c.version_num.type = String(REVISION_CAPACITY)
        return table


def widen_existing_version_table(connection):
    """Widen only a narrow existing bookkeeping column in the migration txn."""
    if connection.dialect.name != "postgresql":
        return
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        return
    column = next(row for row in inspector.get_columns("alembic_version") if row["name"] == "version_num")
    kind = column["type"]
    if not isinstance(kind, String):
        raise RuntimeError("Unexpected Alembic version column type; manual review required")
    # Text/unbounded or a wider existing column must never be narrowed.
    if kind.length is not None and kind.length < REVISION_CAPACITY:
        connection.exec_driver_sql("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
