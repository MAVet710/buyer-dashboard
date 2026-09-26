"""Isolated SQLite guard behavior; PostgreSQL races live in the opt-in gate."""
import importlib
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def guarded():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql("CREATE TABLE cultivation_recipes (id TEXT PRIMARY KEY, organization_id TEXT DEFAULT 'org', facility_id TEXT DEFAULT 'facility', status TEXT, name TEXT)")
            connection.exec_driver_sql("CREATE TABLE cultivation_recipe_stages (id TEXT PRIMARY KEY, organization_id TEXT DEFAULT 'org', facility_id TEXT DEFAULT 'facility', recipe_id TEXT REFERENCES cultivation_recipes(id) ON DELETE RESTRICT, name TEXT)")
            connection.exec_driver_sql("CREATE TABLE cultivation_recipe_targets (id TEXT PRIMARY KEY, organization_id TEXT DEFAULT 'org', facility_id TEXT DEFAULT 'facility', stage_id TEXT REFERENCES cultivation_recipe_stages(id) ON DELETE RESTRICT, value INTEGER)")
            migration = importlib.import_module("migrations.versions.0086_cultivation_intelligence")
            with Operations.context(MigrationContext.configure(connection)):
                migration._recipe_guards()
            for suffix in ("a", "d", "other"):
                connection.execute(sa.text("INSERT INTO cultivation_recipes (id,status,name) VALUES (:id,'draft','Original')"), {"id": suffix})
                connection.execute(sa.text("INSERT INTO cultivation_recipe_stages (id,recipe_id,name) VALUES (:id,:id,'Original')"), {"id": suffix})
                connection.execute(sa.text("INSERT INTO cultivation_recipe_targets (id,stage_id,value) VALUES (:id,:id,20)"), {"id": suffix})
            connection.exec_driver_sql("UPDATE cultivation_recipes SET status='approved' WHERE id='a'")
            yield connection
    finally:
        engine.dispose()


@pytest.mark.parametrize("statement", [
    "UPDATE cultivation_recipes SET name='Changed' WHERE id='a'",
    "UPDATE cultivation_recipes SET status='draft' WHERE id='a'",
    "DELETE FROM cultivation_recipes WHERE id='a'",
    "INSERT INTO cultivation_recipe_stages (id,recipe_id,name) VALUES ('new','a','New')",
    "UPDATE cultivation_recipe_stages SET name='Changed' WHERE id='a'",
    "DELETE FROM cultivation_recipe_stages WHERE id='a'",
    "INSERT INTO cultivation_recipe_targets (id,stage_id,value) VALUES ('new','a',21)",
    "UPDATE cultivation_recipe_targets SET value=21 WHERE id='a'",
    "DELETE FROM cultivation_recipe_targets WHERE id='a'",
])
def test_approved_guards(guarded, statement):
    with pytest.raises(IntegrityError) as error:
        guarded.exec_driver_sql(statement)
    assert str(error.value.orig) == "approved_recipe_immutable"


def test_draft_child_create_update_delete(guarded):
    guarded.exec_driver_sql("INSERT INTO cultivation_recipe_stages (id,recipe_id,name) VALUES ('new','d','New')")
    guarded.exec_driver_sql("INSERT INTO cultivation_recipe_targets (id,stage_id,value) VALUES ('new','new',21)")
    guarded.exec_driver_sql("UPDATE cultivation_recipe_targets SET value=22 WHERE id='new'")
    guarded.exec_driver_sql("UPDATE cultivation_recipe_stages SET name='Edited' WHERE id='new'")
    guarded.exec_driver_sql("UPDATE cultivation_recipe_stages SET id=id,organization_id=organization_id,facility_id=facility_id,recipe_id=recipe_id WHERE id='new'")
    assert guarded.exec_driver_sql("SELECT value FROM cultivation_recipe_targets WHERE id='new'").scalar() == 22
    guarded.exec_driver_sql("DELETE FROM cultivation_recipe_targets WHERE id='new'")
    guarded.exec_driver_sql("DELETE FROM cultivation_recipe_stages WHERE id='new'")


def test_postgres_checks_status_from_locking_query(monkeypatch):
    migration = importlib.import_module("migrations.versions.0086_cultivation_intelligence")
    statements = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=statements.append,
    ))
    migration._recipe_guards()
    functions = [sql for sql in statements if sql.startswith("CREATE FUNCTION")]
    assert len(functions) == 5
    assert not any("SECURITY DEFINER" in sql or "GRANT " in sql for sql in statements)
    for sql in functions:
        if sql.startswith("CREATE FUNCTION ci_guard_"):
            for column in ("id", "organization_id", "facility_id"):
                assert f"OLD.{column} IS DISTINCT FROM NEW.{column}" in sql
            assert sql.index("recipe_parent_immutable") < sql.index("approved_recipe_immutable")
    for sql in functions:
        if "parent_row.status" in sql:
            assert "ORDER BY r.id FOR SHARE" in sql
            assert "FOR KEY SHARE" not in sql
            assert "r.status = 'approved'" not in sql
            assert "WHERE r.id = ANY(parent_ids)" in sql
    triggers = [sql for sql in statements if sql.startswith("CREATE TRIGGER")]
    assert len(triggers) == 5
    for trigger in triggers:
        name = trigger.split("EXECUTE FUNCTION ")[1].split("()")[0]
        assert next(i for i, sql in enumerate(statements) if sql.startswith(f"CREATE FUNCTION {name}()")) < statements.index(trigger)


@pytest.mark.parametrize("source", ["a", "d"])
@pytest.mark.parametrize("table,column", [
    (table, column)
    for table, parent in (("cultivation_recipes", None),
                          ("cultivation_recipe_stages", "recipe_id"),
                          ("cultivation_recipe_targets", "stage_id"))
    for column in ("id", "organization_id", "facility_id") + ((parent,) if parent else ())
])
@pytest.mark.parametrize("destination", ["a", "d", "other", None])
def test_identity_and_parent_are_immutable(guarded, source, table, column, destination):
    before = guarded.exec_driver_sql(f"SELECT {column} FROM {table} WHERE id=?", (source,)).scalar()
    if before == destination:
        destination = "other"
    with pytest.raises(IntegrityError) as error:
        guarded.exec_driver_sql(f"UPDATE {table} SET {column}=? WHERE id=?", (destination, source))
    assert str(error.value.orig) == "recipe_parent_immutable"
    assert guarded.exec_driver_sql(f"SELECT {column} FROM {table} WHERE id=?", (source,)).scalar() == before


@pytest.mark.parametrize("table", ["cultivation_recipes", "cultivation_recipe_stages"])
def test_referenced_draft_delete_is_restricted(guarded, table):
    with pytest.raises(IntegrityError) as error:
        guarded.exec_driver_sql(f"DELETE FROM {table} WHERE id='d'")
    assert str(error.value.orig) == "FOREIGN KEY constraint failed"
    assert guarded.exec_driver_sql(f"SELECT count(*) FROM {table} WHERE id='d'").scalar() == 1


def test_null_safe_identity_noop_and_null_to_value(guarded):
    guarded.exec_driver_sql("INSERT INTO cultivation_recipes (id,status,organization_id,facility_id) VALUES ('null-scope','draft',NULL,NULL)")
    guarded.exec_driver_sql("UPDATE cultivation_recipes SET organization_id=NULL,facility_id=NULL WHERE id='null-scope'")
    with pytest.raises(IntegrityError) as error:
        guarded.exec_driver_sql("UPDATE cultivation_recipes SET organization_id='org' WHERE id='null-scope'")
    assert str(error.value.orig) == "recipe_parent_immutable"
