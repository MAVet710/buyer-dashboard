#!/usr/bin/env python3
"""Run bounded Massachusetts Metrc evaluation evidence from an authorized runtime.

Secrets are read from environment variables and are never written into evidence
files. The first/default mode performs the evaluation's required Facilities
read. Master-data writes are opt-in, sandbox-only, and use the reviewed bounded
payload adapters for location/strain/item create/update.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_master_data import (
    MASTER_DATA_EVALUATION_ACTIONS,
    execute_master_data_evaluation_action,
)


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
    print(f"Passed: {bool(evidence.get('passed'))}")
    print(f"Stage: {evidence.get('stage', '')}")
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
    return {
        "passed": bool(result.get("ok") and int(result.get("http_status") or 0) == 200),
        "stage": "complete" if result.get("ok") else "facilities",
        "operation_type": "facilities",
        "state": "MA",
        "environment": "sandbox",
        "http_status": int(result.get("http_status") or 0),
        "request": {"method": "GET", "path": "facilities/v2/", "query": {}},
        "response": result.get("payload"),
        "records": result.get("records", []),
        "message": result.get("message", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled MA Metrc sandbox evaluation evidence.")
    parser.add_argument("--operation", default="facilities", choices=["facilities", *sorted(MASTER_DATA_EVALUATION_ACTIONS)])
    parser.add_argument("--payload-file", default="", help="JSON object used for a master-data create/update operation.")
    parser.add_argument("--output", default="artifacts/metrc-evaluation/latest.json")
    args = parser.parse_args()

    integrator_key = _secret("METRC_INTEGRATOR_API_KEY")
    user_key = _secret("METRC_USER_API_KEY")

    if args.operation == "facilities":
        evidence = _facilities(integrator_key, user_key)
    else:
        license_number = _secret("METRC_LICENSE_NUMBER")
        if not args.payload_file:
            raise SystemExit("--payload-file is required for a master-data evaluation write.")
        raw = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SystemExit("The payload file must contain one JSON object.")
        evidence = execute_master_data_evaluation_action(
            operation_type=args.operation,
            payload=raw,
            license_number=license_number,
            integrator_api_key=integrator_key,
            user_api_key=user_key,
            state="MA",
            environment="sandbox",
        )

    _write_evidence(args.output, evidence)
    raise SystemExit(0 if evidence.get("passed") else 2)


if __name__ == "__main__":
    main()
