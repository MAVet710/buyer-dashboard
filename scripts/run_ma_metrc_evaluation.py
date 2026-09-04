#!/usr/bin/env python3
"""Run bounded Massachusetts Metrc proficiency-evaluation evidence.

The runner covers every Massachusetts-applicable task family in the 10.2025
Generic Evaluation workbook. It never accepts an arbitrary provider method/path.
Writes are sandbox-only reviewed adapters; list reads walk every provider page.
Secrets are read from environment variables and never written to evidence files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lab import LAB_EVALUATION_ACTIONS, execute_lab_evaluation_action
from services.metrc_evaluation_lifecycle import (
    LIFECYCLE_EVALUATION_ACTIONS,
    execute_lifecycle_evaluation_action,
)
from services.metrc_evaluation_master_data import (
    MASTER_DATA_EVALUATION_ACTIONS,
    execute_master_data_evaluation_action,
)
from services.metrc_evaluation_reads import READ_EVALUATION_ACTIONS, execute_evaluation_read
from services.metrc_evaluation_sales import SALES_EVALUATION_ACTIONS, execute_sales_evaluation_action
from services.metrc_evaluation_transfers import (
    TRANSFER_READ_EVALUATION_ACTIONS,
    TRANSFER_WRITE_EVALUATION_ACTIONS,
    execute_transfer_evaluation_read,
    execute_transfer_template_write,
)
from services.metrc_evaluation_verification import verify_transfer_workbook_read
from services.metrc_evaluation_workbook import ma_workbook_plan


def _secret(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _write_evidence(path: str, evidence: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print(f"Evidence written: {target}")
    if "passed" in evidence:
        print(f"Passed: {bool(evidence.get('passed'))}")
    if evidence.get("stage"):
        print(f"Stage: {evidence.get('stage')}")
    if evidence.get("http_status") is not None:
        print(f"HTTP: {evidence.get('http_status')}")


def _facilities(integrator_key: str, user_key: str) -> dict[str, Any]:
    result = fetch_metrc_resource(
        state="MA",
        user_api_key=user_key,
        integrator_api_key=integrator_key,
        resource="facilities",
        environment="sandbox",
        timeout_seconds=30,
    )
    records = list(result.get("records") or [])
    passed = bool(result.get("ok") and int(result.get("http_status") or 0) == 200 and records)
    return {
        "passed": passed,
        "stage": "complete" if passed else "facilities",
        "operation_type": "facilities",
        "state": "MA",
        "environment": "sandbox",
        "http_status": int(result.get("http_status") or 0),
        "request": {"method": "GET", "path": "facilities/v2/", "query": {}},
        "response": result.get("payload"),
        "records": records,
        "message": (
            "Metrc facilities returned HTTP 200 with verifiable facility/permission records."
            if passed
            else str(result.get("message") or "The facilities workbook row requires at least one verifiable facility record.")
        ),
    }


def _load_payload(path: str, *, required: bool) -> dict[str, Any]:
    if not path:
        if required:
            raise SystemExit("--payload-file is required for this evaluation operation.")
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("The payload file must contain one JSON object.")
    return raw


def main() -> None:
    choices = [
        "workbook_plan",
        "facilities",
        *sorted(MASTER_DATA_EVALUATION_ACTIONS),
        *sorted(READ_EVALUATION_ACTIONS),
        *sorted(LIFECYCLE_EVALUATION_ACTIONS),
        *sorted(LAB_EVALUATION_ACTIONS),
        *sorted(SALES_EVALUATION_ACTIONS),
        *sorted(TRANSFER_READ_EVALUATION_ACTIONS),
        *sorted(TRANSFER_WRITE_EVALUATION_ACTIONS),
    ]
    parser = argparse.ArgumentParser(description="Run controlled MA Metrc sandbox proficiency-evaluation evidence.")
    parser.add_argument("--operation", default="workbook_plan", choices=choices)
    parser.add_argument("--payload-file", default="", help="JSON object for the selected bounded evaluation operation.")
    parser.add_argument("--output", default="artifacts/metrc-evaluation/latest.json")
    args = parser.parse_args()

    if args.operation == "workbook_plan":
        plan = ma_workbook_plan()
        _write_evidence(args.output, plan)
        print(f"Workbook sheets: {plan['sheet_count']}")
        print(f"MA applicable task rows: {plan['applicable_task_count']}")
        return

    integrator_key = _secret("METRC_INTEGRATOR_API_KEY")
    user_key = _secret("METRC_USER_API_KEY")

    if args.operation == "facilities":
        evidence = _facilities(integrator_key, user_key)
    else:
        license_number = _secret("METRC_LICENSE_NUMBER")
        payload_optional = args.operation in {"transfer_rejected"}
        raw = _load_payload(args.payload_file, required=not payload_optional)

        common = {
            "operation_type": args.operation,
            "payload": raw,
            "license_number": license_number,
            "integrator_api_key": integrator_key,
            "user_api_key": user_key,
            "state": "MA",
            "environment": "sandbox",
        }
        if args.operation in MASTER_DATA_EVALUATION_ACTIONS:
            evidence = execute_master_data_evaluation_action(**common)
        elif args.operation in READ_EVALUATION_ACTIONS:
            evidence = execute_evaluation_read(**common)
        elif args.operation in LIFECYCLE_EVALUATION_ACTIONS:
            evidence = execute_lifecycle_evaluation_action(**common)
        elif args.operation in LAB_EVALUATION_ACTIONS:
            evidence = execute_lab_evaluation_action(**common)
        elif args.operation in SALES_EVALUATION_ACTIONS:
            evidence = execute_sales_evaluation_action(**common)
        elif args.operation in TRANSFER_READ_EVALUATION_ACTIONS:
            evidence = verify_transfer_workbook_read(
                args.operation,
                raw,
                execute_transfer_evaluation_read(**common),
            )
        elif args.operation in TRANSFER_WRITE_EVALUATION_ACTIONS:
            evidence = execute_transfer_template_write(**common)
        else:
            raise SystemExit("Selected operation is not wired to a bounded evaluation executor.")

    _write_evidence(args.output, evidence)
    raise SystemExit(0 if evidence.get("passed") else 2)


if __name__ == "__main__":
    main()
