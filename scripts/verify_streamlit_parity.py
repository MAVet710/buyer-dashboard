"""Fail a production web cutover while the Streamlit parity contract is incomplete.

This is intentionally stricter than unit/API parity. The React/FastAPI stack may
be technically healthy while still omitting a workflow, report, permission,
sandbox behavior, or approved UI experience that operators rely on.
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "MIGRATION_PARITY_TRACKER.md"


def main() -> None:
    text = TRACKER.read_text(encoding="utf-8")
    unchecked = [
        re.sub(r"^- \[ \] ", "", line).strip()
        for line in text.splitlines()
        if line.startswith("- [ ] ")
    ]
    if unchecked:
        preview = "\n".join(f"  - {item}" for item in unchecked[:20])
        remainder = len(unchecked) - 20
        suffix = f"\n  ... plus {remainder} more" if remainder > 0 else ""
        raise SystemExit(
            "Production cutover blocked: Streamlit product parity is incomplete.\n"
            f"{preview}{suffix}\n"
            "Complete and validate MIGRATION_PARITY_TRACKER.md before deploying production traffic."
        )
    print("Streamlit product parity gate passed.")


if __name__ == "__main__":
    main()
