from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]
LATEST_REVISION = "0076_global_traceability_ledger"
SUPPLIER_TABLES = {"supplier_portal_grants", "supplier_offers", "supplier_offer_lines"}


def _product_type_check(engine) -> str:
    constraints = inspect(engine).get_check_constraints("coman_products")
    row = next(item for item in constraints if item.get("name") == "ck_coman_product_type")
    return str(row.get("sqltext") or "")


def test_product_label_print_layout_migration_round_trip(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'product-label-layouts.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == LATEST_REVISION
    columns = {column["name"] for column in inspect(engine).get_columns("product_packaging_profiles")}
    assert {"label_layout", "label_width_in", "label_height_in", "label_source_count"} <= columns
    assert "ingredient" in _product_type_check(engine)
    tables = set(inspect(engine).get_table_names())
    assert "alpha_operating_modes" in tables
    assert "integration_provider_snapshots" in tables
    assert "integration_hydration_page_checkpoints" in tables
    assert SUPPLIER_TABLES <= tables

    command.downgrade(config, "0068_label_production_workflow")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0068_label_production_workflow"
    columns = {column["name"] for column in inspect(engine).get_columns("product_packaging_profiles")}
    assert "label_layout" not in columns
    assert "label_source_count" not in columns
    assert "ingredient" not in _product_type_check(engine)
    tables = set(inspect(engine).get_table_names())
    assert "alpha_operating_modes" not in tables
    assert "integration_provider_snapshots" not in tables
    assert "integration_hydration_page_checkpoints" not in tables
    assert not SUPPLIER_TABLES.intersection(tables)

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == LATEST_REVISION
    assert "ingredient" in _product_type_check(engine)
    tables = set(inspect(engine).get_table_names())
    assert "integration_provider_snapshots" in tables
    assert "integration_hydration_page_checkpoints" in tables
    assert SUPPLIER_TABLES <= tables
    engine.dispose()
