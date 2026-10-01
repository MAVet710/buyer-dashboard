"""0091 is additive and preserves recorded recovery/perimeter evidence."""
from pathlib import Path
import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def runner(tmp_path):
    url = "sqlite:///" + (tmp_path / "security-resilience.sqlite3").as_posix()
    env = dict(os.environ, APP_ENV="test", DATABASE_URL=url, COMAN_DATABASE_URL=url,
               PYTHON_DOTENV_DISABLED="1", AI_ALLOW_CLOUD_FALLBACK="false")
    def run(action, target, success=True):
        result = subprocess.run([sys.executable, "-m", "alembic", action, target],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
        assert (result.returncode == 0) is success, (result.stdout + result.stderr)[-5000:]
        return result
    return url, run


def revision(url):
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()


def test_empty_upgrade_and_downgrade(tmp_path):
    url, run = runner(tmp_path)
    run("upgrade", "0090_security_guard")
    run("upgrade", "head")
    assert revision(url) == "0091_security_resilience"
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert "security_source_state" in inspector.get_table_names()
        assert {"recovered_at", "recovery_json"} <= {x["name"] for x in inspector.get_columns("security_incidents")}
        event_columns = {x["name"]: x for x in inspector.get_columns("security_events")}
        assert getattr(event_columns["actor_id"]["type"], "length", None) == 64
        assert {"last_error_category", "last_error_at", "clean_cycles"} <= {
            x["name"] for x in inspector.get_columns("security_monitor_state")
        }
    finally:
        engine.dispose()
    run("downgrade", "0090_security_guard")
    assert revision(url) == "0090_security_guard"


def test_source_evidence_refuses_downgrade(tmp_path):
    url, run = runner(tmp_path)
    run("upgrade", "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO security_source_state
                  (id,checked_at,status,cursor,failures,last_error_category,last_event_at,detail_json)
                VALUES ('windows:defender',1,'observing','10',0,'',1,'{}')
            """))
    finally:
        engine.dispose()
    result = run("downgrade", "0090_security_guard", success=False)
    assert "Preserve the additive schema" in result.stderr
    assert revision(url) == "0091_security_resilience"


def test_recovery_evidence_refuses_downgrade(tmp_path):
    url, run = runner(tmp_path)
    run("upgrade", "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO security_incidents
                  (id,fingerprint,rule,severity,title,group_key,first_seen,last_seen,occurrences,status,version,
                   evidence_json,notification_status,notification_updated_at,notification_reference,notification_attempts,
                   recovered_at,recovery_json)
                VALUES
                  ('i','f','monitoring_degraded','warning','x','worker',1,1,1,'recovered',1,
                   '{}','pending',0,'',0,2,:recovery)
            """), {"recovery": '{"clean_cycles":3}'})
    finally:
        engine.dispose()
    result = run("downgrade", "0090_security_guard", success=False)
    assert "Preserve the additive schema" in result.stderr
    assert revision(url) == "0091_security_resilience"


def test_long_known_account_evidence_refuses_downgrade(tmp_path):
    url, run = runner(tmp_path)
    run("upgrade", "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO security_events
                  (id,occurred_at,kind,subject_key,source_key,actor_id,organization_id,route,request_id,audit_id)
                VALUES
                  ('e',1,'login_failure','subject','source',:actor,'','/login','','')
            """), {"actor": "a" * 64})
    finally:
        engine.dispose()
    result = run("downgrade", "0090_security_guard", success=False)
    assert "Preserve the additive schema" in result.stderr
    assert revision(url) == "0091_security_resilience"
