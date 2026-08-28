"""Deterministic Metrc write adapters for approved traceability actions.

Only explicitly mapped operations are allowed. There is intentionally no generic
"send arbitrary JSON" escape hatch. Every outbound write must name an explicit
sandbox/production environment before a request can leave DoobieLogic.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import requests

from services.metrc_client import resolve_metrc_base_url


class MetrcNativeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        retryable: bool = False,
        response: Any = None,
        request_sent: bool = False,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.retryable = retryable
        self.response = response
        self.request_sent = request_sent


def _environment(value: str) -> str:
    environment = str(value or "").strip().casefold()
    if environment not in {"sandbox", "production"}:
        raise MetrcNativeError("Metrc write execution requires an explicit sandbox or production environment.")
    return environment


def _request(
    *,
    state: str,
    environment: str,
    integrator_api_key: str,
    user_api_key: str,
    method: str,
    path: str,
    payload: Any,
    timeout: int = 30,
) -> dict[str, Any]:
    environment = _environment(environment)
    if not all(str(value or "").strip() for value in (integrator_api_key, user_api_key)):
        raise MetrcNativeError("Metrc integration credentials are incomplete.")
    base, state_code = resolve_metrc_base_url(state)
    if not base:
        raise MetrcNativeError("A valid Metrc state or API base URL is required.")
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    try:
        response = requests.request(
            method.upper(),
            url,
            auth=(integrator_api_key, user_api_key),
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise MetrcNativeError(f"Metrc request failed: {exc}", retryable=True, request_sent=True) from exc
    parsed: Any = None
    if response.content:
        try:
            parsed = response.json()
        except ValueError:
            parsed = {"message": response.text[:1000]}
    if response.status_code == 429:
        raise MetrcNativeError("Metrc rate limited the request.", http_status=429, retryable=True, response=parsed, request_sent=True)
    if response.status_code in {401, 403}:
        raise MetrcNativeError("Metrc rejected the saved API keys or license permissions.", http_status=response.status_code, response=parsed, request_sent=True)
    if response.status_code >= 500:
        raise MetrcNativeError(f"Metrc returned HTTP {response.status_code}.", http_status=response.status_code, retryable=True, response=parsed, request_sent=True)
    if not response.ok:
        raise MetrcNativeError(f"Metrc rejected the operation with HTTP {response.status_code}.", http_status=response.status_code, response=parsed, request_sent=True)
    external_reference = _external_reference(parsed)
    return {
        "http_status": response.status_code,
        "payload": parsed,
        "url_path": path,
        "request_sent": True,
        "environment": environment,
        "state": state_code,
        "external_reference": external_reference,
    }


def _external_reference(payload: Any) -> str:
    candidates: list[Any] = []
    if isinstance(payload, dict):
        candidates.append(payload)
        data = payload.get("Data")
        if isinstance(data, list):
            candidates.extend(row for row in data if isinstance(row, dict))
    elif isinstance(payload, list):
        candidates.extend(row for row in payload if isinstance(row, dict))
    for row in candidates:
        for key in ("Id", "id", "TemplateId", "TransferId", "ManifestNumber"):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def validate_metrc_action(*, operation_type: str, entity_id: str, payload: dict[str, Any], reason: str = "") -> dict[str, Any]:
    operation = str(operation_type or "").strip().casefold()
    entity = str(entity_id or "").strip()
    if not entity:
        raise MetrcNativeError("A Metrc entity ID is required.")
    if operation == "package_finish":
        return {"operation": operation, "body": [{"Label": entity, "ActualDate": str(payload.get("actual_date") or date.today().isoformat())}]}
    if operation == "package_adjust":
        quantity = payload.get("quantity_delta")
        unit = str(payload.get("unit") or "").strip()
        adjustment_reason = str(payload.get("reason") or reason or "").strip()
        if quantity in (None, "") or not unit or not adjustment_reason:
            raise MetrcNativeError("Metrc package adjustment requires quantity_delta, unit, and reason.")
        return {
            "operation": operation,
            "body": [{
                "Label": entity,
                "Quantity": float(quantity),
                "UnitOfMeasure": unit,
                "AdjustmentReason": adjustment_reason,
                "AdjustmentDate": str(payload.get("adjustment_date") or date.today().isoformat()),
                "ReasonNote": str(payload.get("reason_note") or reason or "")[:500],
            }],
        }
    if operation == "transfer_template_create":
        template = payload.get("template")
        if not isinstance(template, dict):
            raise MetrcNativeError("Metrc outgoing transfer-template creation requires a template object.")
        return {"operation": operation, "body": [_validated_transfer_template(template)]}
    raise MetrcNativeError(f"Metrc operation '{operation}' is not enabled for automatic dispatch.")


def _validated_transfer_template(template: dict[str, Any]) -> dict[str, Any]:
    name = str(template.get("Name") or "").strip()
    destinations = template.get("Destinations")
    if not name:
        raise MetrcNativeError("Metrc outgoing transfer template requires Name.")
    if not isinstance(destinations, list) or not destinations:
        raise MetrcNativeError("Metrc outgoing transfer template requires at least one destination.")

    allowed_template_keys = {
        "Name", "DriverLicenseNumber", "DriverName", "DriverOccupationalLicenseNumber",
        "PhoneNumberForQuestions", "TransporterFacilityLicenseNumber", "VehicleLicensePlateNumber",
        "VehicleMake", "VehicleModel", "Destinations",
    }
    clean: dict[str, Any] = {key: template[key] for key in allowed_template_keys if key in template and template[key] not in (None, "")}
    clean_destinations: list[dict[str, Any]] = []
    for raw in destinations:
        if not isinstance(raw, dict):
            raise MetrcNativeError("Every Metrc transfer-template destination must be an object.")
        required = {
            "RecipientLicenseNumber": str(raw.get("RecipientLicenseNumber") or "").strip(),
            "TransferTypeName": str(raw.get("TransferTypeName") or "").strip(),
            "PlannedRoute": str(raw.get("PlannedRoute") or "").strip(),
            "EstimatedDepartureDateTime": str(raw.get("EstimatedDepartureDateTime") or "").strip(),
            "EstimatedArrivalDateTime": str(raw.get("EstimatedArrivalDateTime") or "").strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise MetrcNativeError(f"Metrc transfer-template destination is missing {', '.join(missing)}.")
        packages = raw.get("Packages")
        if not isinstance(packages, list) or not packages:
            raise MetrcNativeError("Metrc transfer-template destination requires at least one package.")
        clean_packages: list[dict[str, Any]] = []
        for package in packages:
            if not isinstance(package, dict):
                raise MetrcNativeError("Every Metrc transfer-template package must be an object.")
            label = str(package.get("PackageLabel") or "").strip()
            if not label:
                raise MetrcNativeError("Every Metrc transfer-template package requires PackageLabel.")
            clean_package: dict[str, Any] = {"PackageLabel": label}
            for key in ("WholesalePrice", "GrossWeight", "GrossUnitOfWeightName"):
                if package.get(key) not in (None, ""):
                    clean_package[key] = package[key]
            clean_packages.append(clean_package)
        destination: dict[str, Any] = {**required, "Packages": clean_packages}
        if raw.get("InvoiceNumber") not in (None, ""):
            destination["InvoiceNumber"] = str(raw.get("InvoiceNumber"))
        transporters = raw.get("Transporters")
        if isinstance(transporters, list) and transporters:
            destination["Transporters"] = [dict(row) for row in transporters if isinstance(row, dict)]
        clean_destinations.append(destination)
    clean["Name"] = name
    clean["Destinations"] = clean_destinations
    return clean


def submit_metrc_action(
    *,
    state: str,
    environment: str,
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    operation_type: str,
    entity_id: str,
    payload: dict[str, Any],
    reason: str = "",
) -> dict[str, Any]:
    environment = _environment(environment)
    validated = validate_metrc_action(operation_type=operation_type, entity_id=entity_id, payload=payload, reason=reason)
    query = f"?licenseNumber={requests.utils.quote(str(license_number).strip(), safe='')}"
    operation = validated["operation"]
    if operation == "transfer_template_create":
        if str(state or "").strip().upper() != "MA" or environment != "sandbox":
            raise MetrcNativeError("Outgoing transfer-template writes are currently enabled only for the Massachusetts Metrc sandbox.")
        method = "POST"
        path = f"transfers/v2/templates/outgoing{query}"
    elif operation == "package_finish":
        method = "PUT"
        path = f"packages/v2/finish{query}"
    else:
        method = "PUT"
        path = f"packages/v2/adjust{query}"
    return _request(
        state=state,
        environment=environment,
        integrator_api_key=integrator_api_key,
        user_api_key=user_api_key,
        method=method,
        path=path,
        payload=validated["body"],
    )
