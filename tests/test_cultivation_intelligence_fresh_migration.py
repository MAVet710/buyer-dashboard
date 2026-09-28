"""Exercise the real historical migration chain, not only current metadata.create_all."""
from pathlib import Path
import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0090_security_guard"


def test_fresh_chain_empty_rollback_and_reupgrade(tmp_path):
    url = "sqlite:///" + (tmp_path / "fresh-cultivation.sqlite").as_posix()
    env = dict(os.environ)
    env.update(APP_ENV="test", DATABASE_URL=url, COMAN_DATABASE_URL=url,
               AI_ALLOW_CLOUD_FALLBACK="false", SANDBOX_STARTUP_SEED_ENABLED="false",
               PYTHONPATH=str(ROOT))
    env.pop("DOOBIELOGIC_TEST_POSTGRES_URL", None)
    env.pop("DOOBIELOGIC_PG_RELEASE_TEST", None)

    def migrate(*arguments):
        result = subprocess.run([sys.executable, "-m", "alembic", *arguments],
                                cwd=ROOT, env=env, capture_output=True, text=True,
                                timeout=90)
        assert result.returncode == 0, (result.stdout + result.stderr)[-7000:]

    def check_revision(expected):
        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
        finally:
            engine.dispose()

    migrate("upgrade", "head")
    check_revision(REVISION)
    engine = create_engine(url)
    try:
        indexes = {row["name"]: row for row in inspect(engine).get_indexes("coman_facilities")}
        scope_index = indexes["uq_ci_coman_facilities_scope"]
        assert scope_index["unique"]
        assert scope_index["column_names"] == ["organization_id", "id"]
        columns = {row["name"]: row for row in inspect(engine).get_columns("cultivation_environment_observations")}
        assert columns["original_value"]["nullable"]
        assert columns["original_unit"]["nullable"]
    finally:
        engine.dispose()
    migrate("downgrade", "-1")
    check_revision("0089_connected_onboarding")
    migrate("downgrade", "-1")
    check_revision("0088_cultivation_radio")
    migrate("downgrade", "-1")
    check_revision("0087_cultivation_push")
    migrate("downgrade", "-1")
    check_revision("0086_cultivation_intelligence")
    migrate("downgrade", "-1")
    check_revision("0085_cultivation_telemetry")
    migrate("upgrade", "head")
    check_revision(REVISION)
