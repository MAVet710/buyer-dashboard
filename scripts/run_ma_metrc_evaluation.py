#!/usr/bin/env python3
"""Run bounded Massachusetts Metrc proficiency-evaluation evidence.

The runner covers every Massachusetts-applicable task family in the 10.2025
Generic Evaluation workbook. It never accepts an arbitrary provider method/path.
Writes are sandbox-only reviewed adapters; list reads walk every provider page.
Secrets are read from environment variables and never written to evidence files.

Evaluation reruns are reuse-only for credentials: this runner has no user-key
bootstrap/provision/rotation path and must use the already-active MA sandbox User
API Key supplied to the process. Every non-context operation also requires an
explicit facility license so Grow/Lab/Sales task families cannot silently share
one stale global sandbox license.
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
from services.metrc_evaluation_instruction_contract import (
    USER_KEY_POLICY,
    ma_instruction_contract,
    operation_facility_profile,
    operation_required_capabilities,
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


def _provider_license(record: dict[str, Any]) -> str:
    """Extract a facility license from normalized or provider-shaped records."""

    queue: list[dict[str, Any]] = [record]
    seen: set[int] = set()
    while queue:
        row = queue.pop(0)
        marker = id(row)
        if marker in seen:
            continue
        seen.add(marker)
        for key in ("license_number", "LicenseNumber", "licenseNumber"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        for key in ("source", "Source", "facility", "Facility", "license", "License"):
            nested = row.get(key)
            if isinstance(nested, dict):
                queue.append(nested)
    return ""


def _provider_capability(record: dict[str, Any], capability: str) -> bool | None:
    """Find one provider capability without assuming top-level vs FacilityType shape."""

    queue: list[dict[str, Any]] = [record]
    seen: set[int] = set()
    while queue:
        row = queue.pop(0)
        marker = id(row)
        if marker in seen:
            continue
        seen.add(marker)
        if capability in row:
            value = row.get(capability)
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            token = str(value or "").strip().casefold()
            if token in {"true", "1", "yes"}:
                return True
            if token in {"false", "0", "no"}:
                return False
        for nested in row.values():
            if isinstance(nested, dict):
                queue.append(nested)
    return None


def _facilities(
    integrator_key: str,
    user_key: str,
    *,
    selected_license: str = "",
    requested_operation: str = "facilities",
) -> dict[str, Any]:
    result = fetch_metrc_resource(
        state="MA",
        user_api_key=user_key,
        integrator_api_key=integrator_key,
        resource="facilities",
        environment="sandbox",
        timeout_seconds=30,
    )
    records = list(result.get("records") or [])
    http_status = int(result.get("http_status") or 0)
    base_passed = bool(result.get("ok") and http_status == 200 and records)
    selected = str(selected_license or "").strip()
    matching = [row for row in records if isinstance(row, dict) and _provider_license(row) == selected] if selected else []
    selected_ok = True if not selected else len(matching) == 1

    operation = str(requested_operation or "facilities").strip().casefold()
    profile = operation_facility_profile(operation)
    required_capabilities = operation_required_capabilities(operation)
    observed_capabilities: dict[str, bool | None] = {}
    capability_ok = True
    if selected and len(matching) == 1 and required_capabilities:
        observed_capabilities = {
            capability: _provider_capability(matching[0], capability)
            for capability in required_capabilities
        }
        # Capability tuples are alternatives for the selected operation/profile.
        capability_ok = any(value is True for value in observed_capabilities.values())

    passed = bool(base_passed and selected_ok and capability_ok)
    if base_passed and selected and not selected_ok:
        message = (
            f"GET /facilities/v2 authenticated, but selected license {selected} matched {len(matching)} facility records; "
            "refusing to continue before any evaluation action."
        )
    elif base_passed and selected and not capability_ok:
        message = (
            f"Selected license {selected} is visible to the active User API Key but does not expose the provider capability "
            f"required for {operation} ({', '.join(required_capabilities)}). Refusing to send the evaluation action."
        )
    elif base_passed:
        message = "Metrc facilities returned HTTP 200 with verifiable facility/permission records."
    else:
        message = str(result.get("message") or "The facilities prerequisite requires at least one verifiable facility record.")
    return {
        "passed": passed,
        "stage": "complete" if passed else "facilities_preflight",
        "operation_type": "facilities",
        "requested_operation": operation,
        "facility_profile": profile,
        "state": "MA",
        "environment": "sandbox",
        "http_status": http_status,
        "request": {"method": "GET", "path": "facilities/v2/", "query": {}},
        "response": result.get("payload"),
        "records": records,
        "selected_license": selected,
        "selected_license_match_count": len(matching) if selected else None,
        "required_capabilities": list(required_capabilities),
        "observed_capabilities": observed_capabilities,
        "credential_policy": dict(USER_KEY_POLICY),
        "message": message,
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


def _attach_safe_policy(evidence: dict[str, Any]) -> dict[str, Any]:
    evidence.setdefault("credential_policy", dict(USER_KEY_POLICY))
    return evidence


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
    parser.add_argument("--license-number", default="", help="Explicit MA sandbox facility license for the selected action. Required for every action except facilities/workbook_plan.")
    parser.add_argument("--payload-file", default="", help="JSON object for the selected bounded evaluation operation.")
    parser.add_argument("--output", default="artifacts/metrc-evaluation/latest.json")
    args = parser.parse_args()

    if args.operation == "workbook_plan":
        plan = ma_workbook_plan()
        plan["submission_context"] = ma_submission_context()
        plan["instruction_contract"] = ma_instruction_contract()
        _write_evidence(args.output, plan)
        print(f"Workbook sheets: {plan['sheet_count']}")
        print(f"MA regulator action rows: {plan['regulator_action_count']}")
        print(f"Mandatory prerequisite checks: {plan['prerequisite_check_count']}")
        print(f"Internal evidence checks: {plan['internal_check_count']}")
        return

    try:
        # The user/vendor key pair is resolved from the existing configured
        # environment only. License routing is intentionally explicit below.
        credentials = resolve_ma_sandbox_evaluation_credentials(require_license=False)
    except MetrcEvaluationCredentialError as exc:
        raise SystemExit(str(exc)) from exc

    integrator_key = credentials.integrator_api_key
    user_key = credentials.user_api_key

    if args.operation == "facilities":
        evidence = _facilities(integrator_key, user_key)
    else:
        license_number = str(args.license_number or "").strip()
        if not license_number:
            raise SystemExit(
                "--license-number is required for evaluation actions. Do not rely on one global sandbox license across Grow, Lab, Sales, and Transfer permission profiles."
            )

        # Mandatory workbook prerequisite and permission/profile safety gate.
        # This uses the existing key pair only; user-key bootstrap/generation is
        # deliberately impossible in this runner.
        preflight = _facilities(
            integrator_key,
            user_key,
            selected_license=license_number,
            requested_operation=args.operation,
        )
        if not preflight.get("passed"):
            preflight.update({
                "network_write_sent": False,
                "message": str(preflight.get("message") or "Facility/permission preflight failed."),
            })
            _write_evidence(args.output, preflight)
            raise SystemExit(2)

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

        evidence.setdefault("facilities_preflight", {
            "passed": True,
            "http_status": preflight.get("http_status"),
            "selected_license": license_number,
            "selected_license_match_count": preflight.get("selected_license_match_count"),
            "facility_profile": preflight.get("facility_profile"),
            "required_capabilities": preflight.get("required_capabilities"),
            "observed_capabilities": preflight.get("observed_capabilities"),
        })

    _write_evidence(args.output, _attach_safe_policy(evidence))
    raise SystemExit(0 if evidence.get("passed") else 2)


if __name__ == "__main__":
    main()
