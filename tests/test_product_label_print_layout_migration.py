from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]


def test_product_label_print_layout_migration_round_trip(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'product-label-layouts.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0070_traceability_object_links"
    columns = {column["name"] for column in inspect(engine).get_columns("product_packaging_profiles")}
    assert {"label_layout", "label_width_in", "label_height_in", "label_source_count"} <= columns

    command.downgrade(config, "0068_label_production_workflow")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0068_label_production_workflow"
    columns = {column["name"] for column in inspect(engine).get_columns("product_packaging_profiles")}
    assert "label_layout" not in columns
    assert "label_source_count" not in columns

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0070_traceability_object_links"
    engine.dispose()
