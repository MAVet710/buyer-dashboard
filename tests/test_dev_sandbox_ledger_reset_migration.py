from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_MIGRATION = ROOT / "migrations" / "versions" / "0029_dev_sandbox_ledger_reset.py"
SQL_MIGRATION = ROOT / "migrations" / "versions" / "0029_dev_sandbox_ledger_reset.sql"


def test_sandbox_ledger_reset_only_bypasses_delete_for_canonical_dev_sandbox():
    source = PY_MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0029_dev_sandbox_ledger_reset"' in source
    assert 'down_revision = "0028_design_partners"' in source
    assert "TG_OP = 'DELETE'" in source
    assert "organization.slug = 'dev-sandbox'" in source
    assert "return OLD" in source
    assert "Inventory ledger entries are immutable" in source
    assert "TG_OP = 'UPDATE'" not in source


def test_sandbox_ledger_guard_function_has_hardened_search_path():
    source = PY_MIGRATION.read_text(encoding="utf-8")
    assert "set search_path = pg_catalog, public" in source


def test_manual_sql_companion_advances_expected_alembic_head():
    source = SQL_MIGRATION.read_text(encoding="utf-8")
    assert "0029_dev_sandbox_ledger_reset" in source
    assert "where version_num='0028_design_partners'" in source
    assert "organization.slug = 'dev-sandbox'" in source
