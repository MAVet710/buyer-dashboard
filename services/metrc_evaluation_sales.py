"""Bounded Massachusetts Metrc sandbox sales evaluation execution.

The proficiency workbook requires receipt create/update/delete and delivery
create/update/complete operations. This module exposes only those six reviewed
method/path pairs. It does not accept arbitrary provider paths or credentials in
evidence, and it refuses execution outside the verified Massachusetts sandbox.

Metrc documents SalesDateTime as facility-local wall-clock time without a time
zone. The adapters therefore reject timestamps carrying Z/UTC offsets rather
than silently shifting a regulated transaction time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_client import fetch_metrc_resource


class MetrcSalesEvaluationError(RuntimeError):
    """Raised when a sales evaluation operation cannot be proven safe."""


@dataclass(frozen=True)
class SalesEvaluationSpec:
    operation_type: str
    method: str
    path: str
    readback_resource: str
    identity_source: str  # response | input | path
    input_id_key: str = "id"
    delete_verification: bool = False


SALES_EVALUATION_ACTIONS: dict[str, SalesEvaluationSpec] = {
    "sales_receipt_create": SalesEvaluationSpec(
        "sales_receipt_create", "POST", "sales/v2/receipts", "sales_receipts_by_id", "response"
    ),
    "sales_receipt_update": SalesEvaluationSpec(
        "sales_receipt_update", "PUT", "sales/v2/receipts", "sales_receipts_by_id", "input"
    ),
    "sales_receipt_delete": SalesEvaluationSpec(
        "sales_receipt_delete", "DELETE", "sales/v2/receipts/{id}", "sales_receipts_by_id", "path",
        delete_verification=True,
    ),
    "sales_delivery_create": SalesEvaluationSpec(
        "sales_delivery_create", "POST", "sales/v2/deliveries", "sales_deliveries_by_id", "response"
    ),
    "sales_delivery_update": SalesEvaluationSpec(
        "sales_delivery_update", "PUT", "sales/v2/deliveries", "sales_deliveries_by_id", "input"
    ),
    "sales_delivery_complete": SalesEvaluationSpec(
        "sales_delivery_complete", "PUT", "sales/v2/deliveries/complete", "sales_deliveries_by_id", "input"
    ),
}


def list_sales_evaluation_actions() -> tuple[SalesEvaluationSpec, ...]:
    return tuple(SALES_EVALUATION_ACTIONS.values())


def _text(payload: dict[str, Any], key: str, label: str, *, optional: bool = False) -> str | None:
    if optional and key not in payload:
        return None
    value = str(payload.get(key) or "").strip()
    if not value and not optional:
        raise MetrcSalesEvaluationError(f"{label} is required.")
    return value or None


def _integer(payload: dict[str, Any], key: str, label: str, *, minimum: int | None = None) -> int:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcSalesEvaluationError(f"{label} is required.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise MetrcSalesEvaluationError(f"{label} must be an integer.") from exc
    if minimum is not None and number < minimum:
        raise MetrcSalesEvaluationError(f"{label} must be at least {minimum}.")
    return number


def _number(payload: dict[str, Any], key: str, label: str, *, minimum: float | None = None) -> float:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcSalesEvaluationError(f"{label} is required.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MetrcSalesEvaluationError(f"{label} must be numeric.") from exc
    if minimum is not None and number < minimum:
        raise MetrcSalesEvaluationError(f"{label} must be at least {minimum}.")
    return number


def _put_optional(row: dict[str, Any], field: str, value: Any) -> None:
    if value is not None and value != "":
        row[field] = value


_OFFSET_PATTERN = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)


def _local_datetime(payload: dict[str, Any], key: str, label: str) -> str:
    value = str(_text(payload, key, label) or "")
    if _OFFSET_PATTERN.search(value):
        raise MetrcSalesEvaluationError(
            f"{label} must be facility-local time without Z or a UTC offset, as required by Metrc."
        )
    if "T" not in value and " " not in value:
        raise MetrcSalesEvaluationError(f"{label} must include both a date and time.")
    return value


def _optional_local_datetime(payload: dict[str, Any], key: str, label: str) -> str | None:
    value = _text(payload, key, label, optional=True)
    if value is None:
        return None
    if _OFFSET_PATTERN.search(value):
        raise MetrcSalesEvaluationError(
            f"{label} must be facility-local time without Z or a UTC offset, as required by Metrc."
        )
    if "T" not in value and " " not in value:
        raise MetrcSalesEvaluationError(f"{label} must include both a date and time.")
    return value


def _transaction(payload: dict[str, Any], *, index: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "PackageLabel": _text(payload, "package_label", f"Transaction {index} package label"),
        "Quantity": _number(payload, "quantity", f"Transaction {index} quantity", minimum=0),
        "UnitOfMeasure": _text(payload, "unit_of_measure", f"Transaction {index} unit of measure"),
        "TotalAmount": _number(payload, "total_amount", f"Transaction {index} total amount", minimum=0),
    }
    text_fields = {
        "city_tax": "CityTax",
        "county_tax": "CountyTax",
        "discount_amount": "DiscountAmount",
        "excise_tax": "ExciseTax",
        "invoice_number": "InvoiceNumber",
        "municipal_tax": "MunicipalTax",
        "price": "Price",
        "qr_codes": "QrCodes",
        "sales_tax": "SalesTax",
        "sub_total": "SubTotal",
        "unit_thc_content_unit_of_measure": "UnitThcContentUnitOfMeasure",
        "unit_weight_unit_of_measure": "UnitWeightUnitOfMeasure",
    }
    for source, target in text_fields.items():
        _put_optional(row, target, _text(payload, source, target, optional=True))
    number_fields = {
        "unit_thc_content": "UnitThcContent",
        "unit_thc_percent": "UnitThcPercent",
        "unit_weight": "UnitWeight",
    }
    for source, target in number_fields.items():
        if payload.get(source) not in (None, ""):
            row[target] = _number(payload, source, target, minimum=0)
    return row


def _transactions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("transactions")
    if not isinstance(raw, list) or not raw:
        raise MetrcSalesEvaluationError("At least one sales transaction is required.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise MetrcSalesEvaluationError(f"Transaction {index} must be an object.")
        rows.append(_transaction(item, index=index))
    return rows


def _receipt_common(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "SalesCustomerType": _text(payload, "sales_customer_type", "Sales customer type"),
        "SalesDateTime": _local_datetime(payload, "sales_date_time", "Sales date/time"),
        "Transactions": _transactions(payload),
    }
    if include_id:
        row["Id"] = _integer(payload, "id", "Sales receipt provider ID", minimum=1)
    for source, target in {
        "caregiver_license_number": "CaregiverLicenseNumber",
        "external_receipt_number": "ExternalReceiptNumber",
        "identification_method": "IdentificationMethod",
        "patient_license_number": "PatientLicenseNumber",
    }.items():
        _put_optional(row, target, _text(payload, source, target, optional=True))
    if payload.get("patient_registration_location_id") not in (None, ""):
        row["PatientRegistrationLocationId"] = _integer(
            payload, "patient_registration_location_id", "Patient registration location ID", minimum=1
        )
    return row


def _build_receipt_create(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_receipt_common(payload, include_id=False)]


def _build_receipt_update(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_receipt_common(payload, include_id=True)]


def _build_receipt_delete(payload: dict[str, Any]) -> None:
    _integer(payload, "id", "Sales receipt provider ID", minimum=1)
    return None


def _delivery_common(payload: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "SalesCustomerType": _text(payload, "sales_customer_type", "Sales customer type"),
        "SalesDateTime": _local_datetime(payload, "sales_date_time", "Sales date/time"),
        "Transactions": _transactions(payload),
    }
    if include_id:
        row["Id"] = _integer(payload, "id", "Sales delivery provider ID", minimum=1)
    text_fields = {
        "driver_employee_id": "DriverEmployeeId",
        "driver_name": "DriverName",
        "drivers_license_number": "DriversLicenseNumber",
        "patient_license_number": "PatientLicenseNumber",
        "phone_number_for_questions": "PhoneNumberForQuestions",
        "planned_route": "PlannedRoute",
        "recipient_address_city": "RecipientAddressCity",
        "recipient_address_county": "RecipientAddressCounty",
        "recipient_address_postal_code": "RecipientAddressPostalCode",
        "recipient_address_state": "RecipientAddressState",
        "recipient_address_street1": "RecipientAddressStreet1",
        "recipient_address_street2": "RecipientAddressStreet2",
        "recipient_name": "RecipientName",
        "transporter_facility_license_number": "TransporterFacilityLicenseNumber",
        "vehicle_license_plate_number": "VehicleLicensePlateNumber",
        "vehicle_make": "VehicleMake",
        "vehicle_model": "VehicleModel",
    }
    for source, target in text_fields.items():
        _put_optional(row, target, _text(payload, source, target, optional=True))
    for source, target in (
        ("estimated_arrival_date_time", "EstimatedArrivalDateTime"),
        ("estimated_departure_date_time", "EstimatedDepartureDateTime"),
    ):
        _put_optional(row, target, _optional_local_datetime(payload, source, target))
    if payload.get("consumer_id") not in (None, ""):
        row["ConsumerId"] = _integer(payload, "consumer_id", "Consumer ID", minimum=1)
    if payload.get("recipient_zone_id") not in (None, ""):
        # Current create schema is numeric; update schemas may return/accept string
        # representations. The evaluation create/update adapter keeps this bounded
        # to a numeric zone id supplied by Metrc discovery.
        row["RecipientZoneId"] = _integer(payload, "recipient_zone_id", "Recipient zone ID", minimum=1)
    return row


def _build_delivery_create(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_delivery_common(payload, include_id=False)]


def _build_delivery_update(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_delivery_common(payload, include_id=True)]


def _string_list(payload: dict[str, Any], key: str, label: str) -> list[str]:
    raw = payload.get(key, [])
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise MetrcSalesEvaluationError(f"{label} must be a list.")
    values = [str(item).strip() for item in raw if str(item).strip()]
    return values


def _returned_packages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("returned_packages", [])
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise MetrcSalesEvaluationError("Returned packages must be a list.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise MetrcSalesEvaluationError(f"Returned package {index} must be an object.")
        row = {
            "Label": _text(item, "label", f"Returned package {index} label"),
            "ReturnQuantityVerified": _integer(
                item, "return_quantity_verified", f"Returned package {index} verified quantity", minimum=0
            ),
            "ReturnReason": _text(item, "return_reason", f"Returned package {index} reason"),
            "ReturnUnitOfMeasure": _text(
                item, "return_unit_of_measure", f"Returned package {index} unit of measure"
            ),
        }
        _put_optional(
            row,
            "ReturnReasonNote",
            _text(item, "return_reason_note", f"Returned package {index} reason note", optional=True),
        )
        rows.append(row)
    return rows


def _build_delivery_complete(payload: dict[str, Any]) -> list[dict[str, Any]]:
    accepted = _string_list(payload, "accepted_packages", "Accepted packages")
    returned = _returned_packages(payload)
    if not accepted and not returned:
        raise MetrcSalesEvaluationError("Complete delivery requires at least one accepted or returned package.")
    return [{
        "Id": _integer(payload, "id", "Sales delivery provider ID", minimum=1),
        "ActualArrivalDateTime": _local_datetime(payload, "actual_arrival_date_time", "Actual arrival date/time"),
        "PaymentType": _text(payload, "payment_type", "Payment type"),
        "AcceptedPackages": accepted,
        "ReturnedPackages": returned,
    }]


_BUILDERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]] | None]] = {
    "sales_receipt_create": _build_receipt_create,
    "sales_receipt_update": _build_receipt_update,
    "sales_receipt_delete": _build_receipt_delete,
    "sales_delivery_create": _build_delivery_create,
    "sales_delivery_update": _build_delivery_update,
    "sales_delivery_complete": _build_delivery_complete,
}


def build_sales_evaluation_payload(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    operation = str(operation_type or "").strip().casefold()
    builder = _BUILDERS.get(operation)
    if builder is None:
        raise MetrcSalesEvaluationError("This operation is not enabled for the MA Metrc sales evaluation.")
    if not isinstance(payload, dict):
        raise MetrcSalesEvaluationError("Evaluation payload must be one JSON object.")
    return builder(payload)


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _collect_ids(value: Any) -> list[str]:
    found: list[str] = []

    def add(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        token = str(value).strip()
        if token and token not in found:
            found.append(token)

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for key in ("Id", "id", "ExternalId", "externalId"):
                if key in node:
                    add(node.get(key))
            for key in ("Ids", "ids", "Data", "data", "Results", "results"):
                if key in node:
                    visit(node.get(key))
        elif isinstance(node, (str, int, float)):
            add(node)

    visit(value)
    return found


def _record_provider_id(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get("provider_id")
        if value is not None and str(value).strip():
            return str(value).strip()
        source = record.get("source")
        if isinstance(source, dict):
            value = source.get("Id") or source.get("id")
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _last_modified(records: Any) -> str:
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("last_modified"):
            return str(record["last_modified"]).strip()
        source = record.get("source")
        if isinstance(source, dict):
            for key in ("LastModified", "lastModified", "LastModifiedDateTime", "Modified", "UpdatedAt"):
                if source.get(key):
                    return str(source[key]).strip()
    return ""


def _provider_id(spec: SalesEvaluationSpec, payload: dict[str, Any], response_payload: Any) -> str:
    if spec.identity_source in {"input", "path"}:
        raw = payload.get(spec.input_id_key)
        return str(raw).strip() if raw is not None else ""
    ids = _collect_ids(response_payload)
    return ids[0] if ids else ""


def _delete_verified(readback: Any, provider_id: str) -> bool:
    if not isinstance(readback, dict):
        return False
    records = readback.get("records")
    # Receipt DELETE archives rather than necessarily removing addressability.
    # Exact matching archived/inactive provider identity is therefore acceptable.
    if readback.get("ok") and _record_provider_id(records) == provider_id:
        return True
    return int(readback.get("http_status") or 0) in {404, 410}


def execute_sales_evaluation_action(
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
    """Execute one reviewed sales proficiency operation and prove the result."""
    operation = str(operation_type or "").strip().casefold()
    spec = SALES_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcSalesEvaluationError("This operation is not enabled for the MA Metrc sales evaluation.")

    environment = str(environment or "").strip().casefold()
    if environment != "sandbox":
        raise MetrcSalesEvaluationError("Sales evaluation writes are restricted to the Metrc sandbox.")
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or not base_url:
        raise MetrcSalesEvaluationError("Sales evaluation writes are restricted to the verified Massachusetts sandbox.")

    license_number = str(license_number or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    user_api_key = str(user_api_key or "").strip()
    if not license_number:
        raise MetrcSalesEvaluationError("A Massachusetts sandbox facility license number is required.")
    if not integrator_api_key or not user_api_key:
        raise MetrcSalesEvaluationError("Both the Metrc integrator/vendor key and sandbox user API key are required.")
    if integrator_api_key == user_api_key:
        raise MetrcSalesEvaluationError("The Metrc integrator/vendor key and sandbox user API key must be distinct credentials.")

    body = build_sales_evaluation_payload(operation, payload)
    provider_id = _provider_id(spec, payload, None)
    path = spec.path.replace("{id}", provider_id) if spec.identity_source == "path" else spec.path
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request_kwargs: dict[str, Any] = {
        "auth": (integrator_api_key, user_api_key),
        "params": {"licenseNumber": license_number},
        "timeout": timeout_seconds,
        "headers": {"Accept": "application/json", "Content-Type": "application/json"},
    }
    if body is not None:
        request_kwargs["json"] = body
    try:
        response = (request_fn or requests.request)(spec.method, url, **request_kwargs)
    except requests.RequestException as exc:
        raise MetrcSalesEvaluationError(
            f"Metrc request failed before evaluation evidence could be captured: {type(exc).__name__}."
        ) from exc

    response_payload = _response_payload(response)
    http_status = int(getattr(response, "status_code", 0) or 0)
    if spec.identity_source == "response":
        provider_id = _provider_id(spec, payload, response_payload)

    evidence: dict[str, Any] = {
        "passed": False,
        "stage": "write",
        "operation_type": operation,
        "state": state_code,
        "environment": environment,
        "license_number": license_number,
        "http_status": http_status,
        "provider_id": provider_id,
        "last_modified": "",
        "request": {"method": spec.method, "path": path, "query": {"licenseNumber": license_number}, "body": body},
        "request_json": _json_text(body),
        "response": response_payload,
        "response_json": _json_text(response_payload),
        "readback": None,
        "message": "",
    }
    if http_status != 200:
        evidence["message"] = f"Metrc returned HTTP {http_status}; the proficiency evaluation requires HTTP 200."
        return evidence
    if not provider_id:
        evidence["stage"] = "readback_identity"
        evidence["message"] = "Metrc accepted the sales write but no exact provider ID was available for fresh readback."
        return evidence

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
    evidence["readback"] = readback
    evidence["last_modified"] = _last_modified(records)

    if spec.delete_verification:
        verified = _delete_verified(readback, provider_id)
    else:
        verified = bool(isinstance(readback, dict) and readback.get("ok") and _record_provider_id(records) == provider_id)
    evidence["passed"] = verified
    evidence["stage"] = "complete" if verified else "readback"
    evidence["message"] = (
        "Metrc returned HTTP 200 and fresh exact provider readback verified the sales mutation."
        if verified
        else "Metrc returned HTTP 200, but fresh exact provider readback did not verify the sales mutation."
    )
    return evidence
