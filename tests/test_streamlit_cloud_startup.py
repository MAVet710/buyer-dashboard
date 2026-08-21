"""Startup/import regression coverage for Streamlit Community Cloud."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_IMPORTS = (
    "services.data_mapping_agent",
    "modules.data_hub",
    "modules.legal_acceptance.policies",
    "modules.legal_acceptance.ui",
    "services.legal_acceptance_store",
)


def _run_import_probe(*, cycles: int) -> subprocess.CompletedProcess[str]:
    code = f"""
import importlib
import sys

targets = {CRITICAL_IMPORTS!r}
for _ in range({cycles}):
    if _:
        for name in list(sys.modules):
            if name == 'modules' or name.startswith('modules.') or name == 'services' or name.startswith('services.'):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()

    for target in targets:
        module = importlib.import_module(target)
        if sys.modules.get(target) is not module:
            raise RuntimeError(f'{{target}} was not retained in sys.modules')
print('startup-import-probe-ok')
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def test_community_cloud_critical_imports_cold_boot():
    result = _run_import_probe(cycles=1)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "startup-import-probe-ok" in result.stdout


def test_community_cloud_critical_imports_survive_clean_reload():
    result = _run_import_probe(cycles=2)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "startup-import-probe-ok" in result.stdout
