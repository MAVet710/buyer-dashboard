"""Controlled Massachusetts Metrc sandbox master-data evaluation execution.

This module exists to bridge DoobieLogic's already-reviewed Facility Setup
payload builders into the official Metrc evaluation without creating a generic
provider write escape hatch. Only the six create/update operations required by
the evaluation for Locations, Strains and Items are executable here, and only
against the explicitly verified Massachusetts sandbox.

Every successful write is followed by the exact v2 by-ID readback added to the
normalized Metrc read registry. The returned evidence is deliberately free of
credentials and is shaped for the evaluation workbook: HTTP status, facility,
provider ID, request JSON, response JSON and fresh readback/LastModified data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import requests

from modules.regulatory.facility_setup_contracts import (
    build_facility_setup_payload,
    get_facility_setup_action,
)
from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_client import fetch_metrc_resource


class MetrcEvaluationError(RuntimeError):
    """Raised when a controlled evaluation operation cannot be proven safe."""


@dataclass(frozen=True)
class MasterDataEvaluationSpec:
    operation_type: str
    method: str
    path: str
    readback_resource: str
    provider_id_field: str = "id"


MASTER_DATA_EVALUATION_ACTIONS: dict[str, MasterDataEvaluationSpec] = {
    "location_create": MasterDataEvaluationSpec("location_create", "POST", "locations/v2/", "locations_by_id"),
    "location_update": MasterDataEvaluationSpec("location_update", "PUT", "locations/v2/", "locations_by_id"),
    "strain_create": MasterDataEvaluationSpec("strain_create", "POST", "strains/v2/", "strains_by_id"),
    "strain_update": MasterDataEvaluationSpec("strain_update", "PUT", "strains/v2/", "strains_by_id"),
    "item_create": MasterDataEvaluationSpec("item_create", "POST", "items/v2/", "items_by_id"),
    "item_update": MasterDataEvaluationSpec("item_update", "PUT", "items/v2/", "items_by_id"),
}


def list_master_data_evaluation_actions() -> tuple[MasterDataEvaluationSpec, ...]:
    return tuple(MASTER_DATA_EVALUATION_ACTIONS.values())


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _provider_id(value: Any) -> str:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, dict):
        candidates.append(value)
        for key in ("Data", "data", "Results", "results"):
            rows = value.get(key)
            if isinstance(rows, list):
                candidates.extend(row for row in rows if isinstance(row, dict))
    elif isinstance(value, list):
        candidates.extend(row for row in value if isinstance(row, dict))
    for row in candidates:
        for key in ("Id", "id", "ExternalId", "externalId"):
            item = row.get(key)
            if item is not None and str(item).strip():
                return str(item).strip()
    return ""


def _last_modified(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get("last_modified")
        if value:
            return str(value).strip()
        source = record.get("source")
        if isinstance(source, dict):
            for key in ("LastModified", "lastModified", "LastModifiedDateTime", "Modified", "UpdatedAt"):
                if source.get(key):
                    return str(source.get(key)).strip()
    return ""


def _readback_provider_id(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get("provider_id")
        if value:
            return str(value).strip()
        source = record.get("source")
        if isinstance(source, dict):
            value = source.get("Id") or source.get("id")
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def execute_master_data_evaluation_action(
    *,
    operation_type: str,
    payload: dict[str, Any],
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    request_fn: Callable[..., Any] | None = None,
    readback_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute one reviewed MA sandbox master-data evaluation action + readback.

    This function never accepts a caller-supplied HTTP method or path. The
    operation name must resolve through both the evaluation whitelist and the
    reviewed Facility Setup catalog, and both contracts must agree before any
    network request is made.
    """

    operation = str(operation_type or "").strip().casefold()
    spec = MASTER_DATA_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcEvaluationError("This operation is not enabled for the MA Metrc master-data evaluation runner.")

    environment = str(environment or "").strip().casefold()
    if environment != "sandbox":
        raise MetrcEvaluationError("Master-data evaluation writes are restricted to the Metrc sandbox.")
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or not base_url:
        raise MetrcEvaluationError("Master-data evaluation writes are restricted to the verified Massachusetts sandbox.")

    license_number = str(license_number or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    user_api_key = str(user_api_key or "").strip()
    if not license_number:
        raise MetrcEvaluationError("A Massachusetts sandbox facility license number is required.")
    if not integrator_api_key or not user_api_key:
        raise MetrcEvaluationError("Both the Metrc integrator/vendor key and sandbox user API key are required.")
    if integrator_api_key == user_api_key:
        raise MetrcEvaluationError("The Metrc integrator/vendor key and sandbox user API key must be distinct credentials.")

    catalog = get_facility_setup_action(operation)
    if catalog is None or catalog.method != spec.method or catalog.path != spec.path:
        raise MetrcEvaluationError("The reviewed Facility Setup contract does not match the evaluation write contract.")
    try:
        body = build_facility_setup_payload(operation, payload)
    except (TypeError, ValueError) as exc:
        raise MetrcEvaluationError(str(exc)) from exc
    if not isinstance(body, list) or not body:
        raise MetrcEvaluationError("The reviewed Facility Setup action did not produce a write payload.")

    url = f"{base_url.rstrip('/')}/{spec.path.lstrip('/')}"
    try:
        response = (request_fn or requests.request)(
            spec.method,
            url,
            auth=(integrator_api_key, user_api_key),
            params={"licenseNumber": license_number},
            json=body,
            timeout=timeout_seconds,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise MetrcEvaluationError(f"Metrc request failed before evaluation evidence could be captured: {type(exc).__name__}.") from exc

    response_payload = _response_payload(response)
    http_status = int(getattr(response, "status_code", 0) or 0)
    if http_status != 200:
        return {
            "passed": False,
            "stage": "write",
            "operation_type": operation,
            "state": state_code,
            "environment": environment,
            "license_number": license_number,
            "http_status": http_status,
            "provider_id": "",
            "last_modified": "",
            "request": {"method": spec.method, "path": spec.path, "query": {"licenseNumber": license_number}, "body": body},
            "request_json": _json_text(body),
            "response": response_payload,
            "response_json": _json_text(response_payload),
            "readback": None,
            "message": f"Metrc returned HTTP {http_status}; the evaluation requires HTTP 200.",
        }

    provider_id = str(payload.get(spec.provider_id_field) or "").strip() if operation.endswith("_update") else ""
    provider_id = provider_id or _provider_id(response_payload)
    if not provider_id:
        return {
            "passed": False,
            "stage": "readback_identity",
            "operation_type": operation,
            "state": state_code,
            "environment": environment,
            "license_number": license_number,
            "http_status": http_status,
            "provider_id": "",
            "last_modified": "",
            "request": {"method": spec.method, "path": spec.path, "query": {"licenseNumber": license_number}, "body": body},
            "request_json": _json_text(body),
            "response": response_payload,
            "response_json": _json_text(response_payload),
            "readback": None,
            "message": "Metrc accepted the write but did not return a provider ID, so by-ID evaluation readback cannot yet be proven.",
        }

    readback = (readback_fn or fetch_metrc_resource)(
        state=state_code,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource=spec.readback_resource,
        environment=environment,
        license_number=license_number,
        path_parameters={"id": provider_id},
        timeout_seconds=timeout_seconds,
    )
    records = readback.get("records") if isinstance(readback, dict) else None
    readback_id = _readback_provider_id(records)
    readback_ok = bool(isinstance(readback, dict) and readback.get("ok") and readback_id == provider_id)

    return {
        "passed": http_status == 200 and readback_ok,
        "stage": "complete" if readback_ok else "readback",
        "operation_type": operation,
        "state": state_code,
        "environment": environment,
        "license_number": license_number,
        "http_status": http_status,
        "provider_id": provider_id,
        "last_modified": _last_modified(records),
        "request": {"method": spec.method, "path": spec.path, "query": {"licenseNumber": license_number}, "body": body},
        "request_json": _json_text(body),
        "response": response_payload,
        "response_json": _json_text(response_payload),
        "readback": readback,
        "message": "Metrc write returned HTTP 200 and the created/updated record was verified by ID." if readback_ok else "Metrc write returned HTTP 200, but exact by-ID readback did not verify the provider object.",
    }
