"""Exact by-ID reads required as standalone rows in the Metrc workbook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from services.metrc_client import fetch_metrc_resource


class MetrcEvaluationReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationReadSpec:
    operation_type: str
    resource: str
    id_key: str = "id"


READ_EVALUATION_ACTIONS: dict[str, EvaluationReadSpec] = {
    "location_get": EvaluationReadSpec("location_get", "locations_by_id"),
    "strain_get": EvaluationReadSpec("strain_get", "strains_by_id"),
    "item_get": EvaluationReadSpec("item_get", "items_by_id"),
}


def execute_evaluation_read(
    *,
    operation_type: str,
    payload: dict[str, Any],
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    fetch_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    operation = str(operation_type or "").strip().casefold()
    spec = READ_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcEvaluationReadError("This by-ID read is not enabled for the MA Metrc evaluation.")
    if str(environment or "").strip().casefold() != "sandbox" or str(state or "").strip().upper() != "MA":
        raise MetrcEvaluationReadError("Evaluation reads are restricted to the Massachusetts Metrc sandbox.")
    provider_id = str(payload.get(spec.id_key) or "").strip()
    if not provider_id:
        raise MetrcEvaluationReadError(f"{spec.id_key} is required for {operation}.")
    result = (fetch_fn or fetch_metrc_resource)(
        state="MA",
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource=spec.resource,
        environment="sandbox",
        license_number=str(license_number or "").strip(),
        path_parameters={"id": provider_id},
        timeout_seconds=timeout_seconds,
    )
    records = result.get("records") if isinstance(result, dict) else []
    observed = ""
    if isinstance(records, list) and records:
        observed = str(records[0].get("provider_id") or "").strip()
    passed = bool(result.get("ok") and int(result.get("http_status") or 0) == 200 and observed == provider_id)
    return {
        "passed": passed,
        "stage": "complete" if passed else "readback",
        "operation_type": operation,
        "state": "MA",
        "environment": "sandbox",
        "license_number": str(license_number or "").strip(),
        "provider_id": provider_id,
        "http_status": int(result.get("http_status") or 0),
        "request": result.get("read_plan", {}),
        "records": records or [],
        "message": "Exact by-ID Metrc read returned HTTP 200 and the requested provider object." if passed else str(result.get("message") or "Exact by-ID read did not verify the requested object."),
    }
