"""Controlled Massachusetts Metrc sandbox cultivation evaluation execution.

The official Metrc proficiency workbook exercises the full cultivation lifecycle:
plant batches -> plants -> harvests.  This module turns that workbook surface into
one bounded adapter.  It never accepts an arbitrary provider method/path and it
never executes outside the explicitly verified Massachusetts sandbox.

Request shapes are based on Metrc's current v2 endpoint surface and the stable
published request contracts for these lifecycle operations.  Each successful
write is followed by a fresh normalized by-ID read when the provider operation
has an object that can be read back.  Evidence is shaped for the evaluation and
never includes credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_client import fetch_metrc_resource


class MetrcCultivationEvaluationError(RuntimeError):
    """Raised when an evaluation cultivation operation cannot be proven safe."""


@dataclass(frozen=True)
class CultivationEvaluationSpec:
    operation_type: str
    method: str
    path: str
    readback_resource: str
    readback_id_key: str = ""
    response_identity: bool = False


CULTIVATION_EVALUATION_ACTIONS: dict[str, CultivationEvaluationSpec] = {
    # Plant Batches
    "plant_batch_create": CultivationEvaluationSpec(
        "plant_batch_create", "POST", "plantbatches/v2/plantings",
        "plant_batches_by_id", response_identity=True,
    ),
    "plant_batch_package": CultivationEvaluationSpec(
        "plant_batch_package", "POST", "plantbatches/v2/packages",
        "packages_by_id", response_identity=True,
    ),
    "plant_batch_growthphase": CultivationEvaluationSpec(
        "plant_batch_growthphase", "POST", "plantbatches/v2/growthphase",
        "plants_by_id", response_identity=True,
    ),
    "plant_batch_destroy": CultivationEvaluationSpec(
        "plant_batch_destroy", "DELETE", "plantbatches/v2/",
        "plant_batches_by_id", readback_id_key="plant_batch_id",
    ),
    # Plants
    "plant_location_update": CultivationEvaluationSpec(
        "plant_location_update", "PUT", "plants/v2/location",
        "plants_by_id", readback_id_key="id",
    ),
    "plant_create_planting": CultivationEvaluationSpec(
        "plant_create_planting", "POST", "plants/v2/plantings",
        "plant_batches_by_id", response_identity=True,
    ),
    "plant_create_batch_package": CultivationEvaluationSpec(
        "plant_create_batch_package", "POST", "plants/v2/plantbatch/packages",
        "packages_by_id", response_identity=True,
    ),
    "plant_destroy": CultivationEvaluationSpec(
        "plant_destroy", "DELETE", "plants/v2/",
        "plants_by_id", readback_id_key="id",
    ),
    "plant_manicure": CultivationEvaluationSpec(
        "plant_manicure", "POST", "plants/v2/manicure",
        "harvests_by_id", response_identity=True,
    ),
    "plant_harvest": CultivationEvaluationSpec(
        "plant_harvest", "PUT", "plants/v2/harvest",
        "harvests_by_id", response_identity=True,
    ),
    # Harvests
    "harvest_package": CultivationEvaluationSpec(
        "harvest_package", "POST", "harvests/v2/packages",
        "packages_by_id", response_identity=True,
    ),
    "harvest_waste": CultivationEvaluationSpec(
        "harvest_waste", "POST", "harvests/v2/waste",
        "harvests_by_id", readback_id_key="id",
    ),
    "harvest_finish": CultivationEvaluationSpec(
        "harvest_finish", "PUT", "harvests/v2/finish",
        "harvests_by_id", readback_id_key="id",
    ),
    "harvest_unfinish": CultivationEvaluationSpec(
        "harvest_unfinish", "PUT", "harvests/v2/unfinish",
        "harvests_by_id", readback_id_key="id",
    ),
}


def list_cultivation_evaluation_actions() -> tuple[CultivationEvaluationSpec, ...]:
    return tuple(CULTIVATION_EVALUATION_ACTIONS.values())


def _text(payload: dict[str, Any], key: str, label: str, *, optional: bool = False) -> str | None:
    if key not in payload and optional:
        return None
    value = str(payload.get(key) or "").strip()
    if not value and not optional:
        raise MetrcCultivationEvaluationError(f"{label} is required.")
    return value or None


def _int(payload: dict[str, Any], key: str, label: str, *, minimum: int | None = None) -> int:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcCultivationEvaluationError(f"{label} is required.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise MetrcCultivationEvaluationError(f"{label} must be an integer.") from exc
    if minimum is not None and number < minimum:
        raise MetrcCultivationEvaluationError(f"{label} must be at least {minimum}.")
    return number


def _number(payload: dict[str, Any], key: str, label: str, *, minimum: float | None = None) -> float:
    value = payload.get(key)
    if value in (None, ""):
        raise MetrcCultivationEvaluationError(f"{label} is required.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MetrcCultivationEvaluationError(f"{label} must be numeric.") from exc
    if minimum is not None and number < minimum:
        raise MetrcCultivationEvaluationError(f"{label} must be at least {minimum}.")
    return number


def _bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"true", "1", "yes", "y"}:
            return True
        if token in {"false", "0", "no", "n", ""}:
            return False
    return bool(value)


def _patient(payload: dict[str, Any]) -> str | None:
    return _text(payload, "patient_license_number", "Patient license number", optional=True)


def _date(payload: dict[str, Any], key: str = "actual_date", label: str = "Actual date") -> str:
    # Metrc accepts ISO-8601 date/date-time strings. Keep the supplied business
    # date exact rather than silently shifting timezone.
    return str(_text(payload, key, label) or "")


def _build_plant_batch_create(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "Name": _text(payload, "name", "Plant batch name"),
        "Type": _text(payload, "type", "Plant batch type"),
        "Count": _int(payload, "count", "Plant count", minimum=1),
        "Strain": _text(payload, "strain", "Strain"),
        "Location": _text(payload, "location", "Location", optional=True),
        "PatientLicenseNumber": _patient(payload),
        "ActualDate": _date(payload),
    }]


def _build_plant_batch_package(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "PlantBatch": _text(payload, "plant_batch", "Plant batch"),
        "Count": _int(payload, "count", "Package plant count", minimum=1),
        "Location": _text(payload, "location", "Location", optional=True),
        "Item": _text(payload, "item", "Item"),
        "Tag": _text(payload, "tag", "Package tag"),
        "PatientLicenseNumber": _patient(payload),
        "Note": _text(payload, "note", "Note", optional=True),
        "IsTradeSample": _bool(payload, "is_trade_sample"),
        "IsDonation": _bool(payload, "is_donation"),
        "ActualDate": _date(payload),
    }]


def _build_plant_batch_growthphase(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "Name": _text(payload, "name", "Plant batch name"),
        "Count": _int(payload, "count", "Plant count", minimum=1),
        "StartingTag": _text(payload, "starting_tag", "Starting plant tag"),
        "GrowthPhase": _text(payload, "growth_phase", "Growth phase"),
        "NewLocation": _text(payload, "new_location", "New location"),
        "GrowthDate": _date(payload, "growth_date", "Growth date"),
        "PatientLicenseNumber": _patient(payload),
    }]


def _build_plant_batch_destroy(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # plant_batch_id is evidence/readback context only and is intentionally not
    # forwarded to Metrc. The provider destroy contract identifies the batch by
    # PlantBatch name plus Count.
    _int(payload, "plant_batch_id", "Plant batch provider ID", minimum=1)
    return [{
        "PlantBatch": _text(payload, "plant_batch", "Plant batch"),
        "Count": _int(payload, "count", "Destroyed plant count", minimum=1),
        "ReasonNote": _text(payload, "reason_note", "Destruction reason"),
        "ActualDate": _date(payload),
    }]


def _identity_pair(payload: dict[str, Any], label: str) -> tuple[int | None, str | None]:
    raw_id = payload.get("id")
    provider_id: int | None = None
    if raw_id not in (None, ""):
        provider_id = _int(payload, "id", f"{label} provider ID", minimum=1)
    value = _text(payload, "label", f"{label} label", optional=True)
    if provider_id is None and not value:
        raise MetrcCultivationEvaluationError(f"{label} provider ID or label is required.")
    return provider_id, value


def _build_plant_location(payload: dict[str, Any]) -> list[dict[str, Any]]:
    provider_id, label = _identity_pair(payload, "Plant")
    row: dict[str, Any] = {
        "Location": _text(payload, "location", "Location"),
        "ActualDate": _date(payload),
    }
    if provider_id is not None:
        row["Id"] = provider_id
    if label:
        row["Label"] = label
    return [row]


def _build_plant_create_planting(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "PlantLabel": _text(payload, "plant_label", "Source plant label", optional=True),
        "PlantBatchName": _text(payload, "plant_batch_name", "New plant batch name"),
        "PlantBatchType": _text(payload, "plant_batch_type", "Plant batch type"),
        "PlantCount": _int(payload, "plant_count", "Plant count", minimum=1),
        "LocationName": _text(payload, "location_name", "Location", optional=True),
        "StrainName": _text(payload, "strain_name", "Strain"),
        "PatientLicenseNumber": _patient(payload),
        "ActualDate": _date(payload),
    }]


def _build_plant_create_batch_package(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "PlantLabel": _text(payload, "plant_label", "Plant label"),
        "PackageTag": _text(payload, "package_tag", "Package tag"),
        "PlantBatchType": _text(payload, "plant_batch_type", "Plant batch type"),
        "Item": _text(payload, "item", "Item"),
        "Location": _text(payload, "location", "Location", optional=True),
        "Note": _text(payload, "note", "Note", optional=True),
        "IsTradeSample": _bool(payload, "is_trade_sample"),
        "PatientLicenseNumber": _patient(payload),
        "IsDonation": _bool(payload, "is_donation"),
        "Count": _int(payload, "count", "Plant count", minimum=1),
        "ActualDate": _date(payload),
    }]


def _build_plant_destroy(payload: dict[str, Any]) -> list[dict[str, Any]]:
    provider_id, label = _identity_pair(payload, "Plant")
    row: dict[str, Any] = {
        "WasteMethodName": _text(payload, "waste_method_name", "Waste method"),
        "WasteMaterialMixed": _text(payload, "waste_material_mixed", "Waste material mixed"),
        "WasteWeight": _number(payload, "waste_weight", "Waste weight", minimum=0),
        "WasteUnitOfMeasureName": _text(payload, "waste_unit_of_measure_name", "Waste unit of measure"),
        "WasteReasonName": _text(payload, "waste_reason_name", "Waste reason"),
        "ReasonNote": _text(payload, "reason_note", "Reason note", optional=True),
        "ActualDate": _date(payload),
    }
    if provider_id is not None:
        row["Id"] = provider_id
    if label:
        row["Label"] = label
    return [row]


def _build_plant_material(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "Plant": _text(payload, "plant", "Plant label"),
        "Weight": _number(payload, "weight", "Weight", minimum=0),
        "UnitOfWeight": _text(payload, "unit_of_weight", "Unit of weight"),
        "DryingLocation": _text(payload, "drying_location", "Drying location"),
        "HarvestName": _text(payload, "harvest_name", "Harvest name", optional=True),
        "PatientLicenseNumber": _patient(payload),
        "ActualDate": _date(payload),
    }]


def _build_harvest_package(payload: dict[str, Any]) -> list[dict[str, Any]]:
    harvest_id = payload.get("harvest_id")
    harvest_name = _text(payload, "harvest_name", "Harvest name", optional=True)
    if harvest_id in (None, "") and not harvest_name:
        raise MetrcCultivationEvaluationError("Harvest provider ID or harvest name is required.")
    ingredient: dict[str, Any] = {
        "HarvestId": None if harvest_id in (None, "") else _int(payload, "harvest_id", "Harvest provider ID", minimum=1),
        "HarvestName": harvest_name,
        "Weight": _number(payload, "weight", "Harvest package weight", minimum=0),
        "UnitOfWeight": _text(payload, "unit_of_weight", "Unit of weight"),
    }
    remediation_steps = payload.get("remediation_steps")
    if remediation_steps is not None:
        if not isinstance(remediation_steps, list):
            raise MetrcCultivationEvaluationError("Remediation steps must be a list.")
        remediation_steps = [str(value).strip() for value in remediation_steps if str(value).strip()]
    return [{
        "Tag": _text(payload, "tag", "Package tag"),
        "Location": _text(payload, "location", "Location", optional=True),
        "Item": _text(payload, "item", "Item"),
        "UnitOfWeight": _text(payload, "unit_of_weight", "Unit of weight"),
        "PatientLicenseNumber": _patient(payload),
        "Note": _text(payload, "note", "Note", optional=True),
        "IsProductionBatch": _bool(payload, "is_production_batch"),
        "ProductionBatchNumber": payload.get("production_batch_number"),
        "IsTradeSample": _bool(payload, "is_trade_sample"),
        "IsDonation": _bool(payload, "is_donation"),
        "ProductRequiresRemediation": _bool(payload, "product_requires_remediation"),
        "RemediateProduct": _bool(payload, "remediate_product"),
        "RemediationMethodId": payload.get("remediation_method_id"),
        "RemediationDate": _text(payload, "remediation_date", "Remediation date", optional=True),
        "RemediationSteps": remediation_steps,
        "ActualDate": _date(payload),
        "Ingredients": [ingredient],
    }]


def _build_harvest_waste(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "Id": _int(payload, "id", "Harvest provider ID", minimum=1),
        "WasteType": _text(payload, "waste_type", "Waste type"),
        "UnitOfWeight": _text(payload, "unit_of_weight", "Unit of weight"),
        "WasteWeight": _number(payload, "waste_weight", "Waste weight", minimum=0),
        "ActualDate": _date(payload),
    }]


def _build_harvest_finish(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "Id": _int(payload, "id", "Harvest provider ID", minimum=1),
        "ActualDate": _date(payload),
    }]


def _build_harvest_unfinish(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"Id": _int(payload, "id", "Harvest provider ID", minimum=1)}]


_BUILDERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "plant_batch_create": _build_plant_batch_create,
    "plant_batch_package": _build_plant_batch_package,
    "plant_batch_growthphase": _build_plant_batch_growthphase,
    "plant_batch_destroy": _build_plant_batch_destroy,
    "plant_location_update": _build_plant_location,
    "plant_create_planting": _build_plant_create_planting,
    "plant_create_batch_package": _build_plant_create_batch_package,
    "plant_destroy": _build_plant_destroy,
    "plant_manicure": _build_plant_material,
    "plant_harvest": _build_plant_material,
    "harvest_package": _build_harvest_package,
    "harvest_waste": _build_harvest_waste,
    "harvest_finish": _build_harvest_finish,
    "harvest_unfinish": _build_harvest_unfinish,
}


def build_cultivation_evaluation_payload(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    operation = str(operation_type or "").strip().casefold()
    builder = _BUILDERS.get(operation)
    if builder is None:
        raise MetrcCultivationEvaluationError("This operation is not enabled for the MA Metrc cultivation evaluation.")
    if not isinstance(payload, dict):
        raise MetrcCultivationEvaluationError("Evaluation payload must be one JSON object.")
    return builder(payload)


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _collect_ids(value: Any) -> list[str]:
    found: list[str] = []

    def add(item: Any) -> None:
        if item is None or isinstance(item, bool):
            return
        token = str(item).strip()
        if token and token not in found:
            found.append(token)

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if isinstance(node, dict):
            for key in ("Id", "id", "ExternalId", "externalId"):
                if key in node:
                    add(node.get(key))
            for key in ("Ids", "ids", "Data", "data", "Results", "results"):
                if key in node:
                    visit(node.get(key))
            return
        if isinstance(node, (int, float, str)):
            add(node)

    visit(value)
    return found


def _records_provider_id(records: Any) -> str:
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


def _readback_id(spec: CultivationEvaluationSpec, input_payload: dict[str, Any], response_payload: Any) -> str:
    if spec.readback_id_key:
        raw = input_payload.get(spec.readback_id_key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    if spec.response_identity:
        ids = _collect_ids(response_payload)
        return ids[0] if ids else ""
    return ""


def execute_cultivation_evaluation_action(
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
    """Execute one whitelisted cultivation evaluation action and verify it."""

    operation = str(operation_type or "").strip().casefold()
    spec = CULTIVATION_EVALUATION_ACTIONS.get(operation)
    if spec is None:
        raise MetrcCultivationEvaluationError("This operation is not enabled for the MA Metrc cultivation evaluation.")

    environment = str(environment or "").strip().casefold()
    if environment != "sandbox":
        raise MetrcCultivationEvaluationError("Cultivation evaluation writes are restricted to the Metrc sandbox.")
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or not base_url:
        raise MetrcCultivationEvaluationError(
            "Cultivation evaluation writes are restricted to the verified Massachusetts sandbox."
        )

    license_number = str(license_number or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    user_api_key = str(user_api_key or "").strip()
    if not license_number:
        raise MetrcCultivationEvaluationError("A Massachusetts sandbox facility license number is required.")
    if not integrator_api_key or not user_api_key:
        raise MetrcCultivationEvaluationError(
            "Both the Metrc integrator/vendor key and sandbox user API key are required."
        )
    if integrator_api_key == user_api_key:
        raise MetrcCultivationEvaluationError(
            "The Metrc integrator/vendor key and sandbox user API key must be distinct credentials."
        )

    body = build_cultivation_evaluation_payload(operation, payload)
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
        raise MetrcCultivationEvaluationError(
            f"Metrc request failed before evaluation evidence could be captured: {type(exc).__name__}."
        ) from exc

    response_payload = _response_payload(response)
    http_status = int(getattr(response, "status_code", 0) or 0)
    evidence: dict[str, Any] = {
        "passed": False,
        "stage": "write",
        "operation_type": operation,
        "state": state_code,
        "environment": environment,
        "license_number": license_number,
        "http_status": http_status,
        "provider_id": "",
        "last_modified": "",
        "request": {
            "method": spec.method,
            "path": spec.path,
            "query": {"licenseNumber": license_number},
            "body": body,
        },
        "request_json": _json_text(body),
        "response": response_payload,
        "response_json": _json_text(response_payload),
        "readback": None,
        "message": "",
    }
    if http_status != 200:
        evidence["message"] = f"Metrc returned HTTP {http_status}; the evaluation requires HTTP 200."
        return evidence

    provider_id = _readback_id(spec, payload, response_payload)
    evidence["provider_id"] = provider_id
    if not provider_id:
        evidence["stage"] = "readback_identity"
        evidence["message"] = (
            "Metrc accepted the write but no verifiable provider ID was available for the required fresh readback."
        )
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
    readback_id = _records_provider_id(records)
    readback_ok = bool(isinstance(readback, dict) and readback.get("ok") and readback_id == provider_id)

    evidence["readback"] = readback
    evidence["last_modified"] = _last_modified(records)
    evidence["passed"] = readback_ok
    evidence["stage"] = "complete" if readback_ok else "readback"
    evidence["message"] = (
        "Metrc write returned HTTP 200 and the regulated object was verified by fresh provider readback."
        if readback_ok
        else "Metrc write returned HTTP 200, but the exact provider object could not be verified by fresh readback."
    )
    return evidence
