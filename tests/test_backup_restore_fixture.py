"""Backup fixture cannot change production roles or bypass restore verification."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / ".github/workflows/database-backup.yml").read_text()


def step(name):
    block = SOURCE.split(f"      - name: {name}\n", 1)[1].split("      - name:", 1)[0]
    return textwrap.dedent(block.split("        run: |\n", 1)[1]).rstrip()


def test_fixture_is_bound_to_disposable_service_and_inert_roles():
    fixture = step("Prepare disposable restore policy roles")
    exact = "postgresql://postgres:restore-test-only@127.0.0.1:5432/buyer_dash_restore"
    assert f"RESTORE_DATABASE_URL: {exact}" in SOURCE
    assert f'[[ "$RESTORE_DATABASE_URL" == "{exact}" ]]' in fixture
    assert fixture.index("exit 1") < fixture.index("docker run")
    assert "current_database() <> 'buyer_dash_restore'" in fixture
    assert "--no-psqlrc --set=ON_ERROR_STOP=1" in fixture
    roles = re.findall(r"CREATE ROLE (\w+) ([^;]+);", fixture)
    assert {name for name, _ in roles} == {"anon", "authenticated", "doobielogic_render_runtime"}
    for _, options in roles:
        assert set(options.split()) == {
            "NOLOGIN", "NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE",
            "NOINHERIT", "NOREPLICATION", "NOBYPASSRLS",
        }
    assert "GRANT " not in fixture
    assert "ALTER " not in fixture
    assert "BEGIN;" in fixture and "COMMIT;" in fixture
    assert SOURCE.index("Prepare disposable restore policy roles") < SOURCE.index("Prove the backup restores")


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="Requires native bash")
@pytest.mark.parametrize("url", [
    "", "postgresql://postgres@db.example.com/postgres",
    "postgresql://postgres:restore-test-only@127.0.0.1:5432/postgres",
    "postgresql://postgres:restore-test-only@127.0.0.1:5432/buyer_dash_restore?host=db.example.com",
])
def test_shell_rejects_unsafe_target_before_docker(tmp_path, url):
    marker = tmp_path / "docker-called"
    fake = tmp_path / "docker"
    fake.write_text(f"#!/bin/bash\ntouch '{marker}'\nexit 99\n")
    fake.chmod(0o700)
    env = {**os.environ, "RESTORE_DATABASE_URL": url, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", "-c", step("Prepare disposable restore policy roles")], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "exact disposable service URL" in result.stdout
    assert not marker.exists()


def test_backup_remains_fail_closed_encrypted_only_and_cleans_passphrase():
    restore = step("Prove the backup restores")
    assert "--exit-on-error" in restore
    assert "--schema=public" in restore
    retain = SOURCE.split("      - name: Retain encrypted backup\n", 1)[1].split("      - name:", 1)[0]
    assert "retention-days: 30" in retain
    assert "if-no-files-found: error" in retain
    assert re.findall(r"^            (.+)$", retain, re.M) == [
        "${{ env.ENCRYPTED_BACKUP_FILE }}",
        "${{ env.ENCRYPTED_BACKUP_FILE }}.sha256",
    ]
    assert "if: always()" in SOURCE.split("      - name: Remove runner backup files", 1)[1]
    cleanup = step("Remove runner backup files")
    assert 'shred --remove "$RUNNER_TEMP/backup-passphrase"' in cleanup
    assert 'shred --remove "$BACKUP_FILE"' in cleanup
