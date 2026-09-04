"""Massachusetts Metrc proficiency evaluation for transfer/wholesale/template tasks.

Workbook labels are preserved in the workbook plan, while execution uses the
current reviewed Metrc v2 paths (not legacy singular ``delivery`` or template
paths). All list reads walk every provider page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_evaluation_pagination import fetch_all_metrc_resource_pages
from services.metrc_native import MetrcNativeError, validate_metrc_action


class MetrcTransferEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TransferReadSpec:
    operation_type: str
    resource: str
    path_parameter_key: str = ""
    require_date_range: bool = False


TRANSFER_READ_EVALUATION_ACTIONS: dict[str, TransferReadSpec] = {
    "transfer_incoming": TransferReadSpec("transfer_incoming", "incoming_transfers", require_date_range=True),
    "transfer_outgoing": TransferReadSpec("transfer_outgoing", "outgoing_transfers", require_date_range=True),
    "transfer_rejected": TransferReadSpec("transfer_rejected", "rejected_transfers"),
    "transfer_deliveries": TransferReadSpec("transfer_deliveries", "transfer_deliveries", "transfer_id"),
    "transfer_delivery_packages": TransferReadSpec("transfer_delivery_packages", "delivery_packages", "delivery_id"),
    "transfer_delivery_packages_wholesale": TransferReadSpec(
        "transfer_delivery_packages_wholesale", "wholesale_delivery_packages", "delivery_id"
    ),
    "transfer_template_list": TransferReadSpec(
        "transfer_template_list", "transfer_templates_outgoing", require_date_range=True
    ),
    "transfer_template_deliveries": TransferReadSpec(
        "transfer_template_deliveries", "transfer_template_deliveries", "template_id"
    ),
}

TRANSFER_WRITE_EVALUATION_ACTIONS = {
    "transfer_template_create": {"method": "POST", "path": "transfers/v2/templates/outgoing"},
    "transfer_template_update": {"method": "PUT", "path": "transfers/v2/templates/outgoing"},
}

TRANSFER_EVALUATION_ACTIONS = {
    **{name: {"kind": "read"} for name in TRANSFER_READ_EVALUATION_ACTIONS},
    **{name: {"kind": "write", **spec} for name, spec in TRANSFER_WRITE_EVALUATION_ACTIONS.items()},
}


def _text(value: Any, label: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise MetrcTransferEvaluationError(f"{label} is required.")
    return clean


def _date_query(payload: dict[str, Any], *, required: bool) -> dict[str, str]:
    start = str(payload.get("last_modified_start") or payload.get("lastModifiedStart") or "").strip()
    end = str(payload.get("last_modified_end") or payload.get("lastModifiedEnd") or "").strip()
    if required and (not start or not end):
        raise MetrcTransferEvaluationError("last_modified_start and last_modified_end are required for this workbook read.")
    query: dict[str, str] = {}
    if start:
        query["lastModifiedStart"] = start
    if end:
        query["lastModifiedEnd"] = end
    return query


def execute_transfer_evaluation_read(
    *,
    operation_type: str,
    payload: dict[str, Any],
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    state: str = "MA",
    environment: str = "sandbox",
    timeout_seconds: int = 30,
    paged_read_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    operation = str(operation_type or "").strip().casefold()
    spec = TRANSFER_READ_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcTransferEvaluationError("This transfer read is not enabled for the MA Metrc evaluation.")
    if str(state or "").strip().upper() != "MA" or str(environment or "").strip().casefold() != "sandbox":
        raise MetrcTransferEvaluationError("Transfer evaluation reads are restricted to the Massachusetts sandbox.")

    path_parameters: dict[str, Any] = {}
    if spec.path_parameter_key:
        value = str(payload.get(spec.path_parameter_key) or "").strip()
        if not value:
            raise MetrcTransferEvaluationError(f"{spec.path_parameter_key} is required for {operation}.")
        path_parameters[spec.path_parameter_key] = value
    query = _date_query(payload, required=spec.require_date_range)
    read = (paged_read_fn or fetch_all_metrc_resource_pages)(
        state="MA",
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource=spec.resource,
        environment="sandbox",
        license_number=str(license_number or "").strip(),
        path_parameters=path_parameters or None,
        query=query or None,
        page_size=20,
        timeout_seconds=timeout_seconds,
    )
    passed = bool(read.get("passed"))
    return {
        "passed": passed,
        "stage": "complete" if passed else "read",
        "operation_type": operation,
        "state": "MA",
        "environment": "sandbox",
        "license_number": str(license_number or "").strip(),
        "http_status": 200 if passed else int((read.get("last_result") or {}).get("http_status") or 0),
        "page_count": int(read.get("page_count") or 0),
        "total_pages": int(read.get("total_pages") or 0),
        "records": read.get("records") or [],
        "readback": read,
        "message": read.get("message", ""),
    }


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _provider_id(value: Any) -> str:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        rows.append(value)
        for key in ("Data", "data", "Results", "results"):
            nested = value.get(key)
            if isinstance(nested, list):
                rows.extend(row for row in nested if isinstance(row, dict))
    elif isinstance(value, list):
        rows.extend(row for row in value if isinstance(row, dict))
    for row in rows:
        for key in ("Id", "id", "TransferTemplateId", "TemplateId"):
            token = str(row.get(key) or "").strip()
            if token:
                return token
    return ""


def _clean_packages(packages: Any) -> list[dict[str, Any]]:
    if not isinstance(packages, list) or not packages:
        raise MetrcTransferEvaluationError("Every transfer-template destination requires at least one package.")
    clean: list[dict[str, Any]] = []
    for raw in packages:
        if not isinstance(raw, dict):
            raise MetrcTransferEvaluationError("Every transfer-template package must be an object.")
        label = _text(raw.get("PackageLabel"), "PackageLabel")
        row: dict[str, Any] = {"PackageLabel": label}
        for key in ("WholesalePrice", "GrossWeight", "GrossUnitOfWeightName"):
            if raw.get(key) not in (None, ""):
                row[key] = raw[key]
        clean.append(row)
    return clean


def _clean_transporters(value: Any) -> list[dict[str, Any]] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        raise MetrcTransferEvaluationError("Transporters must be a list.")
    return [dict(row) for row in value if isinstance(row, dict)]


def _validated_template_update(payload: dict[str, Any]) -> list[dict[str, Any]]:
    template = payload.get("template")
    if not isinstance(template, dict):
        raise MetrcTransferEvaluationError("Template update requires a template object.")
    template_id = template.get("TransferTemplateId", payload.get("transfer_template_id"))
    try:
        template_id = int(template_id)
    except (TypeError, ValueError) as exc:
        raise MetrcTransferEvaluationError("TransferTemplateId must be an integer.") from exc
    destinations = template.get("Destinations")
    if not isinstance(destinations, list) or not destinations:
        raise MetrcTransferEvaluationError("Transfer template update requires at least one destination.")
    clean: dict[str, Any] = {
        "TransferTemplateId": template_id,
        "Name": _text(template.get("Name"), "Template Name"),
    }
    for key in (
        "TransporterFacilityLicenseNumber", "DriverOccupationalLicenseNumber", "DriverName",
        "DriverLicenseNumber", "PhoneNumberForQuestions", "VehicleMake", "VehicleModel",
        "VehicleLicensePlateNumber",
    ):
        if template.get(key) not in (None, ""):
            clean[key] = template[key]

    clean_destinations: list[dict[str, Any]] = []
    for raw in destinations:
        if not isinstance(raw, dict):
            raise MetrcTransferEvaluationError("Every transfer-template destination must be an object.")
        destination_id = raw.get("TransferDestinationId")
        try:
            destination_id = int(destination_id)
        except (TypeError, ValueError) as exc:
            raise MetrcTransferEvaluationError("TransferDestinationId must be an integer for template update.") from exc
        row: dict[str, Any] = {
            "TransferDestinationId": destination_id,
            "RecipientLicenseNumber": _text(raw.get("RecipientLicenseNumber"), "RecipientLicenseNumber"),
            "TransferTypeName": _text(raw.get("TransferTypeName"), "TransferTypeName"),
            "PlannedRoute": _text(raw.get("PlannedRoute"), "PlannedRoute"),
            "EstimatedDepartureDateTime": _text(raw.get("EstimatedDepartureDateTime"), "EstimatedDepartureDateTime"),
            "EstimatedArrivalDateTime": _text(raw.get("EstimatedArrivalDateTime"), "EstimatedArrivalDateTime"),
            "Packages": _clean_packages(raw.get("Packages")),
        }
        if raw.get("InvoiceNumber") not in (None, ""):
            row["InvoiceNumber"] = str(raw.get("InvoiceNumber"))
        transporters = _clean_transporters(raw.get("Transporters"))
        if transporters:
            row["Transporters"] = transporters
        clean_destinations.append(row)
    clean["Destinations"] = clean_destinations
    return [clean]


def _find_template(records: list[dict[str, Any]], provider_id: str) -> dict[str, Any] | None:
    for record in records:
        if str(record.get("provider_id") or "").strip() == provider_id:
            return record
        source = record.get("source") if isinstance(record, dict) else None
        if isinstance(source, dict):
            ids = {
                str(source.get(key) or "").strip()
                for key in ("Id", "id", "TransferTemplateId", "TemplateId")
            }
            if provider_id in ids:
                return record
    return None


def execute_transfer_template_write(
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
    spec = TRANSFER_WRITE_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcTransferEvaluationError("This transfer-template write is not enabled for the MA evaluation.")
    environment = str(environment or "").strip().casefold()
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or environment != "sandbox" or not base_url:
        raise MetrcTransferEvaluationError("Transfer-template evaluation writes are restricted to the Massachusetts sandbox.")
    license_number = str(license_number or "").strip()
    if not license_number:
        raise MetrcTransferEvaluationError("A Massachusetts sandbox license number is required.")
    if not integrator_api_key or not user_api_key or str(integrator_api_key).strip() == str(user_api_key).strip():
        raise MetrcTransferEvaluationError("Distinct Metrc integrator and user API keys are required.")

    try:
        if operation == "transfer_template_create":
            template = payload.get("template")
            entity = str(payload.get("entity_id") or (template or {}).get("Name") or "evaluation-template").strip()
            body = validate_metrc_action(
                operation_type="transfer_template_create",
                entity_id=entity,
                payload={"template": template},
            )["body"]
        else:
            body = _validated_template_update(payload)
    except MetrcNativeError as exc:
        raise MetrcTransferEvaluationError(str(exc)) from exc

    response = (request_fn or requests.request)(
        spec["method"],
        f"{base_url.rstrip('/')}/{spec['path']}",
        auth=(integrator_api_key, user_api_key),
        params={"licenseNumber": license_number},
        json=body,
        timeout=timeout_seconds,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    http_status = int(getattr(response, "status_code", 0) or 0)
    response_payload = _response_payload(response)
    provider_id = (
        str(payload.get("transfer_template_id") or body[0].get("TransferTemplateId") or "").strip()
        if operation == "transfer_template_update"
        else _provider_id(response_payload)
    )
    request_evidence = {
        "method": spec["method"],
        "path": spec["path"],
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
            "provider_id": provider_id,
            "request": request_evidence,
            "request_json": json.dumps(body, separators=(",", ":"), ensure_ascii=False),
            "response": response_payload,
            "message": f"Metrc returned HTTP {http_status}; the proficiency workbook requires HTTP 200.",
        }
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
            "request": request_evidence,
            "response": response_payload,
            "message": "Metrc accepted the template write but no template ID was available for exact readback.",
        }

    read_query = _date_query(payload, required=True)
    read = (paged_read_fn or fetch_all_metrc_resource_pages)(
        state=state_code,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="transfer_templates_outgoing",
        environment=environment,
        license_number=license_number,
        query=read_query,
        page_size=20,
        timeout_seconds=timeout_seconds,
    )
    matched = _find_template(list(read.get("records") or []), provider_id)
    expected_name = str(body[0].get("Name") or "").strip()
    observed_name = ""
    if matched:
        source = matched.get("source") if isinstance(matched, dict) else None
        observed_name = str((source or {}).get("Name") or matched.get("name") or "").strip()
    readback_ok = bool(read.get("passed") and matched and observed_name == expected_name)
    return {
        "passed": readback_ok,
        "stage": "complete" if readback_ok else "readback",
        "operation_type": operation,
        "state": state_code,
        "environment": environment,
        "license_number": license_number,
        "http_status": http_status,
        "provider_id": provider_id,
        "last_modified": str((matched or {}).get("last_modified") or ""),
        "request": request_evidence,
        "request_json": json.dumps(body, separators=(",", ":"), ensure_ascii=False),
        "response": response_payload,
        "readback": read,
        "matched_record": matched,
        "message": "Metrc template write returned HTTP 200 and exact template identity/name was verified across all list pages." if readback_ok else "Metrc accepted the template write, but full paginated template readback did not verify the expected object.",
    }
