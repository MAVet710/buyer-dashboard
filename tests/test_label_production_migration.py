from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]


def test_label_production_migration_upgrades_rolls_back_and_reupgrades(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'label-production-migration.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0068_label_production_workflow"
    tables = set(inspect(engine).get_table_names())
    assert {"label_production_runs", "label_production_sources", "label_production_events"} <= tables

    command.downgrade(config, "-1")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0067_post_harvest_workflow"
    tables = set(inspect(engine).get_table_names())
    assert "label_production_runs" not in tables
    assert "label_production_sources" not in tables
    assert "label_production_events" not in tables

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0068_label_production_workflow"
    engine.dispose()
