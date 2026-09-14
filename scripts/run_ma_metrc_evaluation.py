#!/usr/bin/env python3
"""Run bounded Massachusetts Metrc proficiency-evaluation evidence.

The Generic Evaluation workbook and current MA v2 contracts are the source of
truth. The runner reuses the existing vendor/user API key pair, discovers the
facilities visible to that pair, chooses one exact facility for the selected
workbook action, verifies literal source state, sends only a reviewed
method/path/body, and requires provider readback before claiming a pass.

The Permissions worksheet informs valid Grow/Processor/Labs/Sales access context;
it does not create additional regulator action rows or automatic duplicate writes.
The runner never provisions, rotates, or replaces a Metrc user API key.
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
from services.metrc_evaluation_facility_matrix import (
    FACILITY_FAMILIES,
    MetrcFacilityMatrixError,
    select_facility_for_operation,
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
from services.metrc_evaluation_source_preflight import preflight_workbook_source_state
from services.metrc_evaluation_submission import ma_submission_context
from services.metrc_evaluation_transfers import (
    TRANSFER_READ_EVALUATION_ACTIONS,
    TRANSFER_WRITE_EVALUATION_ACTIONS,
    execute_transfer_evaluation_read,
    execute_transfer_template_write,
)
from services.metrc_evaluation_verification import verify_transfer_workbook_read
from services.metrc_evaluation_workbook import ma_workbook_plan
from services.metrc_evaluation_workbook_contract import (
    MetrcWorkbookContractError,
    WORKBOOK_OPTIONAL_DEPENDENCIES,
    WORKBOOK_PERMISSION_DEPENDENCIES,
    execute_two_plant_harvest_evaluation_action,
    validate_workbook_payload,
    verify_workbook_evidence,
)
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
        max_attempts=1,
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
            "Metrc facilities returned HTTP 200 with verifiable facility records."
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
        "Generic Evaluation 10.2025 contains 46 explicit regulator action rows. DoobieLogic retains "
        "GET /facilities/v2 as one mandatory internal prerequisite so historical evidence numbering remains stable. "
        "The Permissions worksheet D/O grid constrains permission/facility context but does not manufacture extra "
        "action rows or automatic repeated mutations."
    )
    plan["ma_open_loop_context"] = {
        "closed_loop_environment_sheet_required_as_context": True,
        "closed_loop_states_plantbatches_task_sheet_applicable": False,
        "note": (
            "Massachusetts is marked Open Loop=YES and the States worksheet directs evaluators "
            "to the Closed Loop Environment worksheet for beginning-inventory guidance."
        ),
    }
    plan["credential_policy"] = {
        "reuse_existing_user_api_key": True,
        "generate_user_api_key": False,
        "call_integrator_setup": False,
    }
    plan["permission_dependencies"] = {
        "required": {key: list(value) for key, value in WORKBOOK_PERMISSION_DEPENDENCIES.items()},
        "optional": {key: list(value) for key, value in WORKBOOK_OPTIONAL_DEPENDENCIES.items()},
        "facility_families": list(FACILITY_FAMILIES),
        "note": (
            "The D/O grid is retained as access/facility-selection context. Shared sections may require an explicit "
            "facility family to avoid guessing, but the workbook remains 46 regulator action rows."
        ),
    }
    return plan


def _contract_failure(operation: str, message: str, license_number: str = "", stage: str = "workbook_contract") -> dict[str, Any]:
    return {
        "passed": False,
        "stage": stage,
        "operation_type": operation,
        "state": "MA",
        "environment": "sandbox",
        "license_number": license_number,
        "http_status": 0,
        "request_sent": False,
        "message": message,
    }


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
    parser.add_argument(
        "--facility-family",
        default="",
        choices=("", *FACILITY_FAMILIES),
        help=(
            "Permission/facility context for this one workbook action: grow, processor, labs, or sales. "
            "Required only when a shared D/O section is valid in multiple contexts and automatic selection would guess."
        ),
    )
    parser.add_argument(
        "--license-number",
        default="",
        help=(
            "Optional exact sandbox facility license for this action. If omitted, the runner selects "
            "a compatible dedicated facility from the authenticated GET /facilities/v2 response."
        ),
    )
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
        credentials = resolve_ma_sandbox_evaluation_credentials(require_license=False)
    except MetrcEvaluationCredentialError as exc:
        raise SystemExit(str(exc)) from exc

    integrator_key = credentials.integrator_api_key
    user_key = credentials.user_api_key
    facilities = _facilities(integrator_key, user_key)

    if args.operation == "facilities":
        evidence = facilities
    else:
        if not facilities.get("passed"):
            evidence = _contract_failure(
                args.operation,
                "GET /facilities/v2 must return HTTP 200 before an evaluation action is sent.",
            )
            evidence["facilities_preflight"] = {
                "http_status": facilities.get("http_status"),
                "message": facilities.get("message"),
            }
            _write_evidence(args.output, evidence)
            raise SystemExit(2)

        payload_optional = args.operation in {"transfer_rejected"}
        raw = _load_payload(args.payload_file, required=not payload_optional)
        try:
            validate_workbook_payload(args.operation, raw)
            facility = select_facility_for_operation(
                operation_type=args.operation,
                facility_records=list(facilities.get("records") or []),
                facility_family=args.facility_family,
                explicit_license=args.license_number,
            )
        except (MetrcWorkbookContractError, MetrcFacilityMatrixError) as exc:
            evidence = _contract_failure(args.operation, str(exc), args.license_number)
            evidence["facility_family"] = args.facility_family
            _write_evidence(args.output, evidence)
            raise SystemExit(2) from exc

        license_number = str(facility["license_number"])
        try:
            source_preflight = preflight_workbook_source_state(
                operation_type=args.operation,
                payload=raw,
                license_number=license_number,
                integrator_api_key=integrator_key,
                user_api_key=user_key,
            )
        except MetrcWorkbookContractError as exc:
            evidence = _contract_failure(args.operation, str(exc), license_number, stage="source_preflight")
            evidence["facility_preflight"] = facility
            _write_evidence(args.output, evidence)
            raise SystemExit(2) from exc

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
                cached_facilities = {
                    "ok": True,
                    "http_status": 200,
                    "records": list(facilities.get("records") or []),
                }
                evidence = execute_task17_evaluation_action(
                    **common,
                    facilities_read_fn=lambda **_: cached_facilities,
                )
            elif args.operation == "plant_harvest":
                evidence = execute_two_plant_harvest_evaluation_action(
                    payload=raw,
                    license_number=license_number,
                    integrator_api_key=integrator_key,
                    user_api_key=user_key,
                    state="MA",
                    environment="sandbox",
                )
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

        evidence = verify_workbook_evidence(args.operation, raw, evidence)
        evidence["facility_preflight"] = facility
        evidence["facility_family"] = facility["facility_family"]
        evidence["source_preflight"] = source_preflight
        evidence["credential_policy"] = {
            "existing_user_key_reused": True,
            "user_key_generated": False,
            "integrator_setup_called": False,
        }

    _write_evidence(args.output, evidence)
    raise SystemExit(0 if evidence.get("passed") else 2)


if __name__ == "__main__":
    main()
