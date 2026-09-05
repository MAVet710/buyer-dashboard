#!/usr/bin/env python3
"""Build the redacted Massachusetts Metrc evaluation readiness report.

Example:
    python artifacts/metrc-evaluation/finalize_report.py \
        --evidence-dir artifacts/metrc-evaluation/evidence \
        --company-info artifacts/metrc-evaluation/company.local.json

The report never stores Vendor/User API keys. Those belong only in the local
submission workbook created by preserve_workbook.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.metrc_evaluation_finalization import (  # noqa: E402
    MetrcEvaluationFinalizationError,
    build_final_report,
    render_markdown_report,
)


def _load_company_information(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetrcEvaluationFinalizationError(f"Could not read company information {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetrcEvaluationFinalizationError("Company information file must contain one JSON object.")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--company-info", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 2 unless all 47 tasks pass and all non-secret required company fields are present.",
    )
    args = parser.parse_args()

    output_json = args.output_json or args.evidence_dir / "final_report.json"
    output_md = args.output_md or args.evidence_dir / "final_report.md"

    try:
        report = build_final_report(
            evidence_directory=args.evidence_dir,
            company_information=_load_company_information(args.company_info),
        )
    except MetrcEvaluationFinalizationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown_report(report) + "\n", encoding="utf-8")

    summary = report["summary"]
    print(
        f"Metrc evaluation evidence: {summary['passed']}/{summary['total']} passed; "
        f"{summary['failed']} failed; {summary['missing']} missing."
    )
    print(f"Submission status: {report['status']}")
    print(f"JSON: {output_json}")
    print(f"Markdown: {output_md}")
    if args.require_ready and not report["submission_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
