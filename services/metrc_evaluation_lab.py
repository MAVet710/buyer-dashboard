"""Bounded Massachusetts Metrc sandbox lab-result evaluation execution."""

from __future__ import annotations

import json
from typing import Any, Callable

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_evaluation_pagination import fetch_all_metrc_resource_pages


class MetrcLabEvaluationError(RuntimeError):
    pass


LAB_EVALUATION_ACTIONS = {"lab_test_record": {"method": "POST", "path": "labtests/v2/record"}}


def _text(payload: dict[str, Any], key: str, label: str, *, optional: bool = False) -> str | None:
    if optional and key not in payload:
        return None
    value = str(payload.get(key) or "").strip()
    if not value and not optional:
        raise MetrcLabEvaluationError(f"{label} is required.")
    return value or None


def _number(payload: dict[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcLabEvaluationError(f"{label} is required.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MetrcLabEvaluationError(f"{label} must be numeric.") from exc


def build_lab_evaluation_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise MetrcLabEvaluationError("Evaluation payload must be one JSON object.")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise MetrcLabEvaluationError("At least one lab result is required.")
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_results, start=1):
        if not isinstance(raw, dict):
            raise MetrcLabEvaluationError(f"Lab result {index} must be an object.")
        row: dict[str, Any] = {
            "LabTestTypeName": _text(raw, "lab_test_type_name", f"Lab result {index} test type"),
            "Quantity": _number(raw, "quantity", f"Lab result {index} quantity"),
            "Passed": bool(raw.get("passed", False)),
        }
        notes = _text(raw, "notes", f"Lab result {index} notes", optional=True)
        if notes:
            row["Notes"] = notes
        results.append(row)

    body: dict[str, Any] = {
        "Label": _text(payload, "package_label", "Package label"),
        "ResultDate": _text(payload, "result_date", "Result date"),
        "Results": results,
    }
    document_name = _text(payload, "document_file_name", "Document file name", optional=True)
    document_base64 = _text(payload, "document_file_base64", "Document file base64", optional=True)
    if bool(document_name) != bool(document_base64):
        raise MetrcLabEvaluationError("Document file name and base64 content must be supplied together.")
    if document_name:
        body["DocumentFileName"] = document_name
        body["DocumentFileBase64"] = document_base64
    return [body]


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _matches_package(source: dict[str, Any], *, package_id: str, package_label: str) -> bool:
    ids = {str(source.get(key) or "").strip() for key in ("PackageId", "packageId", "Id", "id")}
    labels = {str(source.get(key) or "").strip() for key in ("PackageLabel", "Label", "label")}
    return (package_id and package_id in ids) or (package_label and package_label in labels)


def execute_lab_evaluation_action(
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
    paged_read_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    operation = str(operation_type or "").strip().casefold()
    if operation not in LAB_EVALUATION_ACTIONS:
        raise MetrcLabEvaluationError("This operation is not enabled for the MA Metrc lab evaluation.")
    environment = str(environment or "").strip().casefold()
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or environment != "sandbox" or not base_url:
        raise MetrcLabEvaluationError("Lab evaluation writes are restricted to the verified Massachusetts sandbox.")
    license_number = str(license_number or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    user_api_key = str(user_api_key or "").strip()
    package_id = str(payload.get("package_id") or "").strip()
    package_label = str(payload.get("package_label") or "").strip()
    if not license_number or not package_id:
        raise MetrcLabEvaluationError("License number and existing Metrc package_id are required for lab evaluation readback.")
    if not integrator_api_key or not user_api_key or integrator_api_key == user_api_key:
        raise MetrcLabEvaluationError("Distinct Metrc integrator and user API keys are required.")

    body = build_lab_evaluation_payload(payload)
    path = LAB_EVALUATION_ACTIONS[operation]["path"]
    response = (request_fn or requests.request)(
        "POST",
        f"{base_url.rstrip('/')}/{path}",
        auth=(integrator_api_key, user_api_key),
        params={"licenseNumber": license_number},
        json=body,
        timeout=timeout_seconds,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    http_status = int(getattr(response, "status_code", 0) or 0)
    response_payload = _response_payload(response)
    request_evidence = {
        "method": "POST",
        "path": path,
        "query": {"licenseNumber": license_number},
        "body": body,
    }
    if http_status != 200:
        return {
            "passed": False,
            "stage": "write",
            "operation_type": operation,
            "state": state_code,
            "environment": environment,
            "license_number": license_number,
            "http_status": http_status,
            "request": request_evidence,
            "request_json": json.dumps(body, separators=(",", ":"), ensure_ascii=False),
            "response": response_payload,
            "message": f"Metrc returned HTTP {http_status}; the proficiency workbook requires HTTP 200.",
        }

    read = (paged_read_fn or fetch_all_metrc_resource_pages)(
        state=state_code,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="lab_results",
        environment=environment,
        license_number=license_number,
        query={"packageId": package_id},
        page_size=20,
        timeout_seconds=timeout_seconds,
    )
    expected_types = {
        str(row.get("LabTestTypeName") or "").strip()
        for row in body[0]["Results"]
        if str(row.get("LabTestTypeName") or "").strip()
    }
    observed_types: set[str] = set()
    matching_records: list[dict[str, Any]] = []
    last_modified = ""
    for record in read.get("records") or []:
        source = record.get("source") if isinstance(record, dict) else None
        if not isinstance(source, dict) or not _matches_package(source, package_id=package_id, package_label=package_label):
            continue
        matching_records.append(record)
        for key in ("LabTestTypeName", "TestTypeName", "Name"):
            value = str(source.get(key) or "").strip()
            if value:
                observed_types.add(value)
        last_modified = last_modified or str(record.get("last_modified") or source.get("LastModified") or "").strip()
    readback_ok = bool(read.get("passed") and matching_records and expected_types.issubset(observed_types))
    return {
        "passed": readback_ok,
        "stage": "complete" if readback_ok else "readback",
        "operation_type": operation,
        "state": state_code,
        "environment": environment,
        "license_number": license_number,
        "http_status": http_status,
        "provider_id": package_id,
        "provider_label": package_label,
        "last_modified": last_modified,
        "request": request_evidence,
        "request_json": json.dumps(body, separators=(",", ":"), ensure_ascii=False),
        "response": response_payload,
        "readback": read,
        "matching_records": matching_records,
        "message": "Metrc lab result returned HTTP 200 and exact package-scoped test evidence was found across all pages." if readback_ok else "Metrc accepted the lab result, but full paginated readback did not verify the expected package/test evidence.",
    }
