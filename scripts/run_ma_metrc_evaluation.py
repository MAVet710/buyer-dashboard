#!/usr/bin/env python3
"""Run bounded Massachusetts Metrc proficiency-evaluation evidence.

The runner covers every Massachusetts-applicable task family in the 10.2025
Generic Evaluation workbook. It never accepts an arbitrary provider method/path.
Writes are sandbox-only reviewed adapters; list reads walk every provider page.
Secrets are read from environment variables and never written to evidence files.

The regulator workbook contains 46 explicit action rows. DoobieLogic retains one
additional internal prerequisite entry for GET /facilities/v2 so historical
evidence numbering remains stable. Evaluation reruns consume the existing saved
vendor/user key pair only; provisioning and user-key generation are separate,
explicit admin actions and are never invoked by this runner.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_credentials import (
    MetrcEvaluationCredentialError,
    resolve_ma_sandbox_evaluation_credentials,
)
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
from services.metrc_evaluation_submission import ma_submission_context
from services.metrc_evaluation_transfers import (
    TRANSFER_READ_EVALUATION_ACTIONS,
    TRANSFER_WRITE_EVALUATION_ACTIONS,
    execute_transfer_evaluation_read,
    execute_transfer_template_write,
)
from services.metrc_evaluation_verification import verify_transfer_workbook_read
from services.metrc_evaluation_workbook import ma_workbook_plan
from services.metrc_task17_preflight import TASK17_OPERATION, execute_task17_evaluation_action


REGULATOR_ACTION_ROW_COUNT = 46
INTERNAL_PREREQUISITE_COUNT = 1


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
            else str(result.get("message") or "The facilities prerequisite requires at least one verifiable facility record.")
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


def _annotate_workbook_plan(plan: dict[str, Any]) -> dict[str, Any]:
    plan["regulator_action_row_count"] = REGULATOR_ACTION_ROW_COUNT
    plan["internal_prerequisite_count"] = INTERNAL_PREREQUISITE_COUNT
    plan["internal_check_count"] = int(plan.get("applicable_task_count") or 0)
    plan["counting_note"] = (
        "Generic Evaluation 10.2025 contains 46 explicit regulator action rows. "
        "DoobieLogic retains GET /facilities/v2 as one mandatory internal prerequisite, "
        "so historical evidence uses 47 internal checks without claiming that the regulator workbook has 47 action rows."
    )
    plan["ma_open_loop_context"] = {
        "closed_loop_environment_sheet_required_as_context": True,
        "closed_loop_states_plantbatches_task_sheet_applicable": False,
        "note": (
            "Massachusetts is marked Open Loop=YES and the States sheet directs evaluators "
            "to the Closed Loop Environment sheet for starting-inventory guidance."
        ),
    }
    plan["credential_policy"] = {
        "reuse_existing_user_api_key": True,
        "generate_user_api_key": False,
        "call_integrator_setup": False,
        "note": (
            "This runner is Postman-equivalent: it consumes the existing vendor key, existing user key, "
            "exact licenseNumber, reviewed endpoint, and reviewed payload. It never provisions or rotates credentials."
        ),
    }
    return plan


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
        plan = _annotate_workbook_plan(ma_workbook_plan())
        plan["submission_context"] = ma_submission_context()
        _write_evidence(args.output, plan)
        print(f"Workbook sheets: {plan['sheet_count']}")
        print(f"Regulator action rows: {plan['regulator_action_row_count']}")
        print(f"Internal prerequisite checks: {plan['internal_prerequisite_count']}")
        return

    try:
        credentials = resolve_ma_sandbox_evaluation_credentials(
            require_license=args.operation != "facilities"
        )
    except MetrcEvaluationCredentialError as exc:
        raise SystemExit(str(exc)) from exc

    integrator_key = credentials.integrator_api_key
    user_key = credentials.user_api_key

    if args.operation == "facilities":
        evidence = _facilities(integrator_key, user_key)
    else:
        license_number = credentials.license_number
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
            if args.operation == TASK17_OPERATION:
                evidence = execute_task17_evaluation_action(**common)
            else:
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
