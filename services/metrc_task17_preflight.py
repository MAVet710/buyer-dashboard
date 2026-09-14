"""Fail-closed facility capability preflight for Massachusetts Metrc Task 17."""

from __future__ import annotations

from typing import Any, Callable

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import execute_lifecycle_evaluation_action
from services.metrc_facility_capabilities import provider_capability


TASK17_OPERATION = "plant_plantbatch_packages"
TASK17_CAPABILITY = "CanCreateImmaturePlantPackagesFromPlants"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _facility_license(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    for key in ("license_number", "LicenseNumber", "licenseNumber", "Number", "number"):
        value = _text(record.get(key))
        if value:
            return value
    source = record.get("source")
    if isinstance(source, dict):
        for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
            value = _text(source.get(key))
            if value:
                return value
        nested = source.get("License") or source.get("license")
        if isinstance(nested, dict):
            for key in ("Number", "number", "LicenseNumber", "licenseNumber"):
                value = _text(nested.get(key))
                if value:
                    return value
    return ""


def task17_facility_capability_preflight(
    *,
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    facilities_read_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Require fresh exact facility evidence before Task 17 can mutate Metrc."""

    license_value = _text(license_number)
    state_code = _text(state).upper()
    environment_code = _text(environment).casefold()
    base = {
        "passed": False,
        "stage": "facility_capability",
        "operation_type": TASK17_OPERATION,
        "state": state_code,
        "environment": environment_code,
        "license_number": license_value,
        "http_status": 0,
        "request": {"method": "GET", "path": "facilities/v2/", "query": {}},
        "capability": TASK17_CAPABILITY,
        "capability_value": None,
        "matching_facility_count": 0,
        "write_sent": False,
        "message": "",
    }
    if state_code != "MA" or environment_code != "sandbox" or not license_value:
        base["message"] = "Task 17 is restricted to one exact Massachusetts sandbox facility license."
        return base
    if not _text(integrator_api_key) or not _text(user_api_key):
        base["message"] = "Task 17 capability preflight requires both Metrc credentials."
        return base

    reader = facilities_read_fn or fetch_metrc_resource
    result = reader(
        state=state_code,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="facilities",
        environment=environment_code,
        timeout_seconds=timeout_seconds,
        max_attempts=1,
    )
    if not isinstance(result, dict):
        base["message"] = "Task 17 capability preflight returned an invalid facility response; no write was sent."
        return base

    base["http_status"] = int(result.get("http_status") or 0)
    if not result.get("ok") or base["http_status"] != 200:
        reason = _text(result.get("message")) or "Fresh facility discovery failed."
        base["message"] = f"Task 17 capability preflight failed: {reason} No write was sent."
        return base

    records = [dict(row) for row in result.get("records") or [] if isinstance(row, dict)]
    matches = [row for row in records if _facility_license(row) == license_value]
    base["matching_facility_count"] = len(matches)
    if len(matches) != 1:
        base["message"] = (
            "Task 17 capability preflight could not identify exactly one matching Metrc facility; no write was sent."
        )
        return base

    capability = provider_capability(matches[0], TASK17_CAPABILITY)
    base["capability_value"] = capability
    if capability is False:
        base["message"] = (
            f"Metrc facility {license_value} explicitly reports {TASK17_CAPABILITY}=false; Task 17 write was not sent."
        )
        return base
    if capability is not True:
        base["message"] = (
            f"Metrc facility {license_value} does not explicitly enable {TASK17_CAPABILITY}; Task 17 write was not sent."
        )
        return base

    base["passed"] = True
    base["message"] = (
        f"Fresh facility evidence explicitly enables {TASK17_CAPABILITY}; Task 17 may proceed under normal write authorization."
    )
    return base


def execute_task17_evaluation_action(
    *,
    operation_type: str,
    payload: dict[str, Any],
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    facilities_read_fn: Callable[..., dict[str, Any]] | None = None,
    lifecycle_execute_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run Task 17 only after a fresh exact facility capability preflight passes."""

    operation = _text(operation_type).casefold()
    if operation != TASK17_OPERATION:
        raise ValueError("The Task 17 guarded executor only accepts plant_plantbatch_packages.")

    preflight = task17_facility_capability_preflight(
        license_number=license_number,
        integrator_api_key=integrator_api_key,
        user_api_key=user_api_key,
        state=state,
        environment=environment,
        timeout_seconds=timeout_seconds,
        facilities_read_fn=facilities_read_fn,
    )
    if preflight.get("passed") is not True:
        return preflight

    executor = lifecycle_execute_fn or execute_lifecycle_evaluation_action
    evidence = executor(
        operation_type=TASK17_OPERATION,
        payload=payload,
        license_number=license_number,
        integrator_api_key=integrator_api_key,
        user_api_key=user_api_key,
        state=state,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    if isinstance(evidence, dict):
        evidence["facility_capability_preflight"] = {
            "http_status": preflight["http_status"],
            "license_number": preflight["license_number"],
            "capability": TASK17_CAPABILITY,
            "capability_value": True,
            "matching_facility_count": 1,
        }
    return evidence
