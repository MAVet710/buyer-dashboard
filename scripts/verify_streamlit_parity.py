"""Enforce the Streamlit -> DoobieLogic parity contract.

There are two intentionally different gates:

* ``contract`` runs on every PR/CI build. It verifies that the strict parity
  contract is present, authoritative, machine-readable, and cannot silently
  fall back to the obsolete migration tracker while restoration is still in
  progress.
* ``release`` runs before production deployment. It blocks deployment while
  any strict source/behavior/visual item or binding legacy-evidence item is
  still unchecked.

This separation lets the restoration branch stay testable while making it
impossible to ship a technically healthy but incomplete React rewrite again.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STRICT_AUDIT = ROOT / "STREAMLIT_EXACT_PARITY_AUDIT.md"
LEGACY_EVIDENCE = ROOT / "LEGACY_STREAMLIT_PRODUCT_EVIDENCE.md"
OBSOLETE_TRACKER = ROOT / "MIGRATION_PARITY_TRACKER.md"

REQUIRED_AUDIT_SECTIONS = (
    "## Global shell",
    "## Home",
    "## Retail / Buyer Operations",
    "## Production Ops",
    "## Commercial Ops",
    "## Compliance / Traceability",
    "## Data & Settings",
    "## Reports",
    "## Release gate",
)

REQUIRED_CONTRACT_PHRASES = (
    "A React page does **not** pass merely because an equivalent API or a page with the same name exists.",
    "No item may be checked because of an intentional redesign.",
)

REQUIRED_EVIDENCE_PHRASES = (
    "Buyer Dash` was the working/development name of this same application",
    "The intended production product name is **DoobieLogic**",
    "A checked item in `STREAMLIT_EXACT_PARITY_AUDIT.md` is reopened if operator evidence demonstrates missing composition or behavior.",
)

CHECKBOX = re.compile(r"^- \[(?P<state>[ xX])\] (?P<label>.+)$")


def _read(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Parity contract missing required file: {path.name}")
    return path.read_text(encoding="utf-8")


def _checkbox_rows(text: str) -> list[tuple[bool, str]]:
    rows: list[tuple[bool, str]] = []
    for line in text.splitlines():
        match = CHECKBOX.match(line)
        if match:
            rows.append((match.group("state").lower() == "x", match.group("label").strip()))
    return rows


def _validate_contract(strict_text: str, evidence_text: str) -> None:
    missing_sections = [section for section in REQUIRED_AUDIT_SECTIONS if section not in strict_text]
    if missing_sections:
        raise SystemExit("Strict parity audit is missing required sections: " + ", ".join(missing_sections))

    missing_contract = [phrase for phrase in REQUIRED_CONTRACT_PHRASES if phrase not in strict_text]
    if missing_contract:
        raise SystemExit("Strict parity audit lost non-redesign protections: " + " | ".join(missing_contract))

    missing_evidence = [phrase for phrase in REQUIRED_EVIDENCE_PHRASES if phrase not in evidence_text]
    if missing_evidence:
        raise SystemExit("Legacy evidence contract lost binding product rules: " + " | ".join(missing_evidence))

    if "MIGRATION_PARITY_TRACKER.md" not in evidence_text or "must not be used by itself" not in evidence_text:
        raise SystemExit("Parity contract must explicitly prevent the obsolete tracker from declaring completion.")

    strict_rows = _checkbox_rows(strict_text)
    evidence_rows = _checkbox_rows(evidence_text)
    if not strict_rows:
        raise SystemExit("Strict parity audit contains no machine-readable checklist items.")
    if not evidence_rows:
        raise SystemExit("Legacy Streamlit evidence contains no machine-readable acceptance items.")

    checked = sum(done for done, _ in strict_rows) + sum(done for done, _ in evidence_rows)
    open_count = sum(not done for done, _ in strict_rows) + sum(not done for done, _ in evidence_rows)
    print(f"Parity contract valid: {checked} verified item(s), {open_count} open item(s).")


def _release_gate(strict_text: str, evidence_text: str) -> None:
    unresolved: list[tuple[str, str]] = []
    unresolved.extend((STRICT_AUDIT.name, label) for done, label in _checkbox_rows(strict_text) if not done)
    unresolved.extend((LEGACY_EVIDENCE.name, label) for done, label in _checkbox_rows(evidence_text) if not done)
    if unresolved:
        preview = "\n".join(f"  - {source}: {label}" for source, label in unresolved[:30])
        remainder = len(unresolved) - 30
        suffix = f"\n  ... plus {remainder} more" if remainder > 0 else ""
        raise SystemExit(
            "Production deployment blocked: DoobieLogic Streamlit parity is incomplete.\n"
            f"{preview}{suffix}\n"
            "Resolve every strict/source/visual acceptance item before production cutover."
        )
    print("Production Streamlit -> DoobieLogic parity release gate passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the Streamlit -> DoobieLogic product parity contract.")
    parser.add_argument("--mode", choices=("contract", "release"), default="contract")
    args = parser.parse_args()

    strict_text = _read(STRICT_AUDIT)
    evidence_text = _read(LEGACY_EVIDENCE)
    _read(OBSOLETE_TRACKER)  # retained as history only; never authoritative here.

    _validate_contract(strict_text, evidence_text)
    if args.mode == "release":
        _release_gate(strict_text, evidence_text)


if __name__ == "__main__":
    main()
