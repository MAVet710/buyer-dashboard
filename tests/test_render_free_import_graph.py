from __future__ import annotations

import json
import subprocess
import sys


def test_ai_runtime_import_does_not_eager_load_data_science_graph() -> None:
    """Normal FastAPI startup must not pay for AI-only pandas/provider imports."""
    script = r'''
import json
import sys
import backend.app.services.ai_runtime  # noqa: F401
print(json.dumps({
    "pandas": "pandas" in sys.modules,
    "ai_datasets": "backend.app.services.ai_datasets" in sys.modules,
    "google_genai": "google.genai" in sys.modules,
}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    state = json.loads(completed.stdout.strip().splitlines()[-1])
    assert state == {
        "pandas": False,
        "ai_datasets": False,
        "google_genai": False,
    }
