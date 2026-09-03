from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine


ROOT = Path(__file__).resolve().parents[1]


def test_post_harvest_migration_upgrades_rolls_back_and_reupgrades(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'post-harvest-migration.db').as_posix()}"
    monkeypatch.setenv("COMAN_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url, future=True)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0067_post_harvest_workflow"

    command.downgrade(config, "-1")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0066_metrc_guide_v11_alignment"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0067_post_harvest_workflow"
    engine.dispose()
