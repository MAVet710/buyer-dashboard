from __future__ import annotations

import json
import subprocess
import sys


def test_po_router_does_not_eager_load_reportlab() -> None:
    script = r'''
import json
import sys
import backend.app.routers.po_parity  # noqa: F401
print(json.dumps({"reportlab": any(name == "reportlab" or name.startswith("reportlab.") for name in sys.modules)}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    state = json.loads(completed.stdout.strip().splitlines()[-1])
    assert state == {"reportlab": False}
