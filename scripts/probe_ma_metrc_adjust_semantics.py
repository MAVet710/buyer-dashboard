#!/usr/bin/env python3
"""Decide PUT /packages/v2/adjust semantics on a disposable MA sandbox package.

One write, on a package chosen because losing it costs nothing, answers the
question that blocks Packages Step 3: does Metrc treat the Quantity field as a
signed delta or as the package's new balance?  The anomalous package is named
here only so the probe can refuse to touch it.

Credentials come from the environment exactly as the evaluation runner reads
them, and are never printed or written to evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.metrc_adjust_semantics_probe import (  # noqa: E402
    ABSOLUTE,
    DELTA,
    MetrcAdjustSemanticsProbeError,
    probe_package_adjust_semantics,
)
from services.metrc_evaluation_credentials import (  # noqa: E402
    MetrcEvaluationCredentialError,
    resolve_ma_sandbox_evaluation_credentials,
)

WRITE_CONFIRMATION = "I_APPROVE_MA_SANDBOX_WRITE"

# Packages Step 3's anomalous package.  Listed so the probe fails closed if it
# is ever passed as the probe target.
DEFAULT_QUARANTINED_PACKAGE_IDS = ("64801",)
DEFAULT_QUARANTINED_PACKAGE_LABELS = ("AAA0A0300001A30000000041",)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=10
    )
    return completed.stdout.strip()


def _require_current_origin_main() -> str:
    head = _git("rev-parse", "HEAD")
    origin_main = _git("rev-parse", "origin/main")
    if not head or head != origin_main:
        raise RuntimeError(
            "MA sandbox writes are blocked because this checkout is not the exact current origin/main commit."
        )
    return head


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove whether PUT /packages/v2/adjust takes a delta or an absolute quantity."
    )
    parser.add_argument("--package-id", required=True, help="Provider ID of the disposable probe package.")
    parser.add_argument("--package-label", required=True, help="Exact tag of the disposable probe package.")
    parser.add_argument("--license-number", required=True)
    parser.add_argument("--adjustment-reason", required=True, help="An exact reason from GET /packages/v2/adjust/reasons.")
    parser.add_argument("--adjustment-date", required=True, help="YYYY-MM-DD.")
    parser.add_argument("--unit-of-measure", default="", help="Defaults to the probe package's own unit.")
    parser.add_argument("--probe-quantity", type=float, default=None, help="Defaults to a safe distinguishing value.")
    parser.add_argument("--reason-note", default="")
    parser.add_argument("--quarantine-package-id", action="append", default=[])
    parser.add_argument("--quarantine-package-label", action="append", default=[])
    parser.add_argument(
        "--quarantined-observed-quantity",
        type=float,
        default=-5.0,
        help="Quantity the anomalous package currently reports, used to derive its corrective write.",
    )
    parser.add_argument("--output", default="artifacts/metrc-evaluation/adjust-semantics-probe.json")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()

    if args.confirmation != WRITE_CONFIRMATION:
        raise RuntimeError(f"MA Metrc sandbox writes require confirmation: {WRITE_CONFIRMATION}")
    head = _require_current_origin_main()

    try:
        credentials = resolve_ma_sandbox_evaluation_credentials(require_license=False)
    except MetrcEvaluationCredentialError as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        evidence = probe_package_adjust_semantics(
            package_id=args.package_id,
            package_label=args.package_label,
            adjustment_reason=args.adjustment_reason,
            adjustment_date=args.adjustment_date,
            license_number=args.license_number,
            integrator_api_key=credentials.integrator_api_key,
            user_api_key=credentials.user_api_key,
            quarantined_package_ids=DEFAULT_QUARANTINED_PACKAGE_IDS + tuple(args.quarantine_package_id),
            quarantined_package_labels=DEFAULT_QUARANTINED_PACKAGE_LABELS + tuple(args.quarantine_package_label),
            quarantined_observed_quantity=args.quarantined_observed_quantity,
            unit_of_measure=args.unit_of_measure,
            probe_quantity=args.probe_quantity,
            reason_note=args.reason_note,
        )
    except MetrcAdjustSemanticsProbeError as exc:
        raise RuntimeError(str(exc)) from exc

    evidence["checkout_commit"] = head
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

    print(f"verdict: {evidence['verdict']}")
    print(f"probe package {evidence['probe_package_id']}: {evidence['current_quantity']} "
          f"-> sent Quantity={evidence['probe_quantity']} -> read back {evidence['observed_quantity']}")
    print(f"  delta would predict {evidence['predicted_if_delta']}; absolute would predict {evidence['predicted_if_absolute']}")
    print(evidence["message"])
    if evidence["verdict"] in {ABSOLUTE, DELTA} and evidence["recommended_correction"] is not None:
        print(f"corrective Quantity for the quarantined package: {evidence['recommended_correction']}")
    if evidence["probe_restoration_quantity"] is not None:
        print(f"send Quantity={evidence['probe_restoration_quantity']} to restore the probe package")
    print(f"evidence written to {output}")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
