from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


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


def test_fastapi_lifespan_does_not_reconcile_persistent_dev_fixtures() -> None:
    """Persistent sandbox data preparation must not block each Render Free wake."""
    source = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    lifespan = source.split("async def lifespan", 1)[1].split("app = FastAPI", 1)[0]
    assert "sync_sandbox_retail_sales" not in source
    assert "ensure_rich_extraction_sandbox" not in source
    assert "get_engine()" not in lifespan
