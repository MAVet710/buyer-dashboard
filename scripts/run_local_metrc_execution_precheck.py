#!/usr/bin/env python3
"""Run the local Massachusetts Metrc GET-only execution precheck.

This command is intentionally Metrc-only. It does not inspect or gate on the
DoobieLogic application login, including the `God` username. DoobieLogic auth is
diagnosed separately by `scripts/diagnose_local_username_login.py`.

The command combines the two existing read-only Massachusetts diagnostics:

- evaluation rebaseline: locations, strains, items, plant batches, plants,
  harvests, sales receipts/deliveries, outgoing transfer templates, available
  tags, and live transfer types;
- resume diagnostic: facilities/capability evidence, active/lab packages,
  lab types, sales customer types, and incoming/outgoing/rejected transfers.

It never generates or rotates Metrc keys, never calls sandbox integrator setup,
and never sends POST/PUT/DELETE provider mutations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

# When Python executes a file by path, sys.path[0] is the file's directory
# (`scripts/`) rather than the repository root. Insert the root before importing
# the application packages so this script works both from PowerShell and tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Settings
from backend.app.database import get_engine
from backend.app.services.metrc_evaluation_rebaseline import run_server_evaluation_rebaseline
from backend.app.services.metrc_resume_diagnostics import run_server_resume_diagnostic


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return completed.stdout.strip()
    except Exception:
        return "unknown"


def _default_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"local-metrc-{stamp}"[:36]


def _failed(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "failed",
        "read_only": True,
        "mutations_sent": 0,
        "secrets_included": False,
    }


def _run_read_only(
    runner: Callable[[Any, Settings, str], dict[str, Any]],
    *,
    engine: Any,
    settings: Settings,
    run_id: str,
) -> tuple[dict[str, Any], str]:
    try:
        return runner(engine, settings, run_id), ""
    except Exception as exc:
        # Preserve only the class. Provider/database connection strings,
        # credentials and secret-bearing exception text must not enter evidence.
        return _failed(run_id), type(exc).__name__


def _healthy(result: dict[str, Any]) -> bool:
    # Ready means this invocation returned fresh facility evidence. Reusing a
    # completed run ID is intentionally not treated as execution-ready because
    # the returned sentinel does not contain the prior provider snapshot.
    return bool(
        result.get("read_only") is True
        and int(result.get("mutations_sent") or 0) == 0
        and int(result.get("facility_count") or 0) > 0
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the PC-hosted GET-only Massachusetts Metrc execution precheck."
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path. Defaults to artifacts/metrc-evaluation/local-metrc-precheck-<run-id>.json.",
    )
    args = parser.parse_args()

    run_id = str(args.run_id or _default_run_id()).strip()[:36]
    engine = get_engine()
    settings = Settings()

    rebaseline, rebaseline_error = _run_read_only(
        run_server_evaluation_rebaseline,
        engine=engine,
        settings=settings,
        run_id=run_id,
    )
    blocker_snapshot, blocker_error = _run_read_only(
        run_server_resume_diagnostic,
        engine=engine,
        settings=settings,
        run_id=run_id,
    )

    rebaseline_ok = _healthy(rebaseline)
    blocker_ok = _healthy(blocker_snapshot)
    metrc_ok = bool(rebaseline_ok and blocker_ok)

    result = {
        "schema_version": 2,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "scope": "metrc_evaluation_only",
        "doobielogic_login_checked": False,
        "doobielogic_login_required_for_precheck": False,
        "evaluation_rebaseline": rebaseline,
        "evaluation_rebaseline_error_class": rebaseline_error,
        "blocker_snapshot": blocker_snapshot,
        "blocker_snapshot_error_class": blocker_error,
        "coverage": {
            "facilities_and_task17_capability": True,
            "locations_strains_items_plant_batches_plants_harvests": True,
            "active_and_lab_packages": True,
            "package_and_plant_tags": True,
            "lab_types_and_sales_customer_types": True,
            "sales_receipts_and_deliveries": True,
            "incoming_outgoing_rejected_transfers": True,
            "outgoing_transfer_templates": True,
            "transfer_types": True,
        },
        "metrc_precheck_healthy": metrc_ok,
        "provider_mutations_sent": 0,
        "metrc_credentials_changed": False,
        "integrator_setup_called": False,
        "ready_for_family_execution_plan": metrc_ok,
    }

    output = Path(args.output) if args.output else Path(
        f"artifacts/metrc-evaluation/local-metrc-precheck-{run_id}.json"
    )
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"Evidence written: {output}")
    raise SystemExit(0 if result["ready_for_family_execution_plan"] else 2)


if __name__ == "__main__":
    main()
