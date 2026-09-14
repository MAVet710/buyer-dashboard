"""Literal Generic Evaluation 10.2025 execution contract for Massachusetts.

This module sits in front of provider execution.  It deliberately separates the
Metrc API schema (what the API will accept) from the proficiency workbook
contract (what the evaluator actually asked the integrator to demonstrate).

The evaluation runner must reuse the existing vendor/user key pair.  This module
never provisions credentials and never calls a sandbox setup endpoint.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import requests

from backend.app.services.metrc_harvest_readback import verify_plant_harvested
from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import build_lifecycle_evaluation_payload
from services.metrc_facility_capabilities import (
    provider_boolean_capabilities,
    provider_facility_license,
)


class MetrcWorkbookContractError(RuntimeError):
    """Raised before dispatch when the literal workbook task is not satisfied."""


PERMISSION_FAMILIES = ("grow", "processor", "labs", "sales")

# The prose table headed "Dependent REQUIRED Permissions per Facility" is used
# here because it is more explicit than the D/O grid (the workbook itself has a
# couple of inconsistent cells, e.g. Labs/Strains and Sales Deliveries).
SECTION_REQUIRED_FAMILIES: dict[str, frozenset[str]] = {
    "locations": frozenset({"grow"}),
    "strains": frozenset({"grow", "processor", "labs", "sales"}),
    "plant_batches_plants": frozenset({"grow"}),
    "harvests": frozenset({"grow"}),
    "items": frozenset({"grow", "processor", "sales"}),
    "packages": frozenset({"grow", "processor", "labs", "sales"}),
    "labs": frozenset({"labs"}),
    "sales": frozenset({"sales"}),
    "sales_deliveries": frozenset({"sales"}),
    "transfers": frozenset({"grow", "processor", "labs", "sales"}),
    # Transfer Templates are optional for every permission family.  The MA States
    # sheet still marks the task sheet applicable, so one explicit family context
    # is required for evidence, but it is not treated as a D dependency.
    "transfer_templates": frozenset(),
}

OPERATION_SECTION: dict[str, str] = {
    "location_create": "locations",
    "location_update": "locations",
    "location_get": "locations",
    "strain_create": "strains",
    "strain_update": "strains",
    "strain_get": "strains",
    "item_create": "items",
    "item_update": "items",
    "item_get": "items",
    "plant_batch_plantings": "plant_batches_plants",
    "plant_batch_packages": "plant_batches_plants",
    "plant_batch_growthphase": "plant_batches_plants",
    "plant_batch_delete": "plant_batches_plants",
    "plant_location": "plant_batches_plants",
    "plant_plantings": "plant_batches_plants",
    "plant_plantbatch_packages": "plant_batches_plants",
    "plant_delete": "plant_batches_plants",
    "plant_manicure": "plant_batches_plants",
    "plant_harvest": "plant_batches_plants",
    "harvest_packages": "harvests",
    "harvest_waste": "harvests",
    "harvest_finish": "harvests",
    "harvest_unfinish": "harvests",
    "package_create": "packages",
    "package_item": "packages",
    "package_adjust": "packages",
    "package_finish": "packages",
    "package_unfinish": "packages",
    "lab_test_record": "labs",
    "sales_receipt_create": "sales",
    "sales_receipt_update": "sales",
    "sales_receipt_delete": "sales",
    "sales_delivery_create": "sales_deliveries",
    "sales_delivery_update": "sales_deliveries",
    "sales_delivery_complete": "sales_deliveries",
    "transfer_incoming": "transfers",
    "transfer_outgoing": "transfers",
    "transfer_rejected": "transfers",
    "transfer_deliveries": "transfers",
    "transfer_delivery_packages": "transfers",
    "transfer_delivery_packages_wholesale": "transfers",
    "transfer_template_create": "transfer_templates",
    "transfer_template_list": "transfer_templates",
    "transfer_template_deliveries": "transfer_templates",
    "transfer_template_update": "transfer_templates",
}


def required_families(operation_type: str) -> tuple[str, ...]:
    section = OPERATION_SECTION.get(str(operation_type or "").strip().casefold())
    if not section:
        return ()
    return tuple(sorted(SECTION_REQUIRED_FAMILIES[section]))


def resolve_permission_family(operation_type: str, requested: str = "") -> str:
    operation = str(operation_type or "").strip().casefold()
    section = OPERATION_SECTION.get(operation)
    if not section:
        raise MetrcWorkbookContractError(f"No workbook permission section is registered for {operation!r}.")

    requested = str(requested or "").strip().casefold()
    if requested:
        if requested not in PERMISSION_FAMILIES:
            raise MetrcWorkbookContractError(
                f"permission family must be one of {', '.join(PERMISSION_FAMILIES)}."
            )
        required = SECTION_REQUIRED_FAMILIES[section]
        if required and requested not in required:
            raise MetrcWorkbookContractError(
                f"{operation} is not a required {requested} permission-family task in the workbook."
            )
        return requested

    required = SECTION_REQUIRED_FAMILIES[section]
    if len(required) == 1:
        return next(iter(required))
    if not required:
        raise MetrcWorkbookContractError(
            f"{operation} is an optional Transfer Template task; provide --permission-family explicitly for evidence."
        )
    raise MetrcWorkbookContractError(
        f"{operation} is required for multiple facility families ({', '.join(sorted(required))}); "
        "provide --permission-family so the workbook evidence is facility-specific."
    )


def _cap_true(capabilities: dict[str, bool], *names: str) -> bool:
    return any(capabilities.get(name) is True for name in names)


def facility_supports_family(record: Any, permission_family: str) -> bool:
    family = str(permission_family or "").strip().casefold()
    capabilities = provider_boolean_capabilities(record)
    if family == "grow":
        return capabilities.get("CanGrowPlants") is True and capabilities.get("CanTrackVegetativePlants") is True
    if family == "processor":
        return capabilities.get("CanInfuseProducts") is True
    if family == "labs":
        return capabilities.get("CanTestPackages") is True
    if family == "sales":
        can_sell = _cap_true(
            capabilities,
            "CanSellToConsumers",
            "CanSellToPatients",
            "CanSellToCaregivers",
            "CanSellToExternalPatients",
        )
        can_deliver = _cap_true(
            capabilities,
            "CanDeliverSalesToConsumers",
            "CanDeliverSalesToPatients",
            "CanDeliverSalesToCaregivers",
        )
        return can_sell and can_deliver
    return False


def validate_facility_family(
    *,
    operation_type: str,
    permission_family: str,
    license_number: str,
    facility_records: list[dict[str, Any]],
) -> dict[str, Any]:
    family = resolve_permission_family(operation_type, permission_family)
    wanted = str(license_number or "").strip()
    matches = [row for row in facility_records if provider_facility_license(row) == wanted]
    if len(matches) != 1:
        raise MetrcWorkbookContractError(
            f"Expected exactly one GET /facilities/v2 record for {wanted}; observed {len(matches)}."
        )
    record = matches[0]
    capabilities = provider_boolean_capabilities(record)
    if not facility_supports_family(record, family):
        raise MetrcWorkbookContractError(
            f"Facility {wanted} does not expose the capability profile required for the workbook's {family} family."
        )
    return {
        "permission_family": family,
        "license_number": wanted,
        "capabilities": capabilities,
        "verified_from": "GET /facilities/v2/",
    }


def _int(payload: dict[str, Any], key: str) -> int | None:
    try:
        return int(payload.get(key))
    except (TypeError, ValueError):
        return None


def _number(payload: dict[str, Any], key: str) -> float | None:
    try:
        return float(payload.get(key))
    except (TypeError, ValueError):
        return None


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def validate_workbook_payload(operation_type: str, payload: dict[str, Any]) -> None:
    """Fail before provider dispatch when an API-valid payload misses the workbook task."""

    operation = str(operation_type or "").strip().casefold()
    if not isinstance(payload, dict):
        raise MetrcWorkbookContractError("Workbook evaluation payload must be one JSON object.")

    if operation == "location_update" and not str(payload.get("name") or "").strip():
        raise MetrcWorkbookContractError("Location Step 2 must change/provide the location Name.")
    if operation == "strain_update":
        if payload.get("indica_percentage") in (None, "") or payload.get("sativa_percentage") in (None, ""):
            raise MetrcWorkbookContractError(
                "Strains Step 2 must provide both IndicaPercentage and SativaPercentage."
            )
    if operation == "item_update" and not str(payload.get("unit_of_measure") or "").strip():
        raise MetrcWorkbookContractError("Items Step 2 must change/provide UnitOfMeasure.")

    exact_counts = {
        "plant_batch_plantings": ("count", 6, "Plant Batches Step 1 must create a batch containing 6 plants."),
        "plant_batch_packages": ("count", 3, "Plant Batches Step 2 must package 3 clones from the batch."),
        "plant_batch_growthphase": ("count", 2, "Plant Batches Step 3 must move 2 plants to Vegetative."),
        "plant_batch_delete": ("count", 1, "Plant Batches Step 4 must destroy 1 plant."),
        "plant_delete": ("count", 1, "Plants Step 4 must destroy 1 plant."),
    }
    if operation in exact_counts:
        key, expected, message = exact_counts[operation]
        if _int(payload, key) != expected:
            raise MetrcWorkbookContractError(message)
    if operation == "plant_batch_growthphase" and str(payload.get("growth_phase") or "").strip().casefold() != "vegetative":
        raise MetrcWorkbookContractError("Plant Batches Step 3 must set GrowthPhase to Vegetative.")

    if operation == "plant_harvest":
        plants = _list(payload, "plants")
        if len(plants) != 2 or not all(isinstance(row, dict) for row in plants):
            raise MetrcWorkbookContractError("Plants Step 6 must harvest exactly the 2 remaining plants.")
        harvest_name = str(payload.get("harvest_name") or "").strip()
        actual_date = str(payload.get("actual_date") or "").strip()
        if not harvest_name or not actual_date:
            raise MetrcWorkbookContractError("Plants Step 6 requires one shared HarvestName and ActualDate.")
        ids: set[str] = set()
        labels: set[str] = set()
        for index, row in enumerate(plants, start=1):
            plant_id = str(row.get("id") or "").strip()
            label = str(row.get("plant") or row.get("label") or "").strip()
            if not plant_id or not label:
                raise MetrcWorkbookContractError(
                    f"Plants Step 6 plant {index} requires provider id and plant label for exact readback."
                )
            ids.add(plant_id)
            labels.add(label)
        if len(ids) != 2 or len(labels) != 2:
            raise MetrcWorkbookContractError("Plants Step 6 requires two distinct source plants.")

    if operation == "harvest_waste":
        waste_type = str(payload.get("waste_type") or "").strip().casefold()
        if "moisture" in waste_type:
            raise MetrcWorkbookContractError("Harvest Step 2 explicitly says moisture loss is NOT removed as waste.")

    if operation == "package_adjust":
        target = _number(payload, "expected_final_quantity")
        if target is None or abs(target) > 1e-9:
            raise MetrcWorkbookContractError(
                "Packages Step 3 must declare expected_final_quantity=0 so readback can prove the package was adjusted to zero."
            )

    if operation in {"sales_delivery_create", "sales_delivery_update"}:
        customer = str(payload.get("sales_customer_type") or "").strip().casefold()
        if customer not in {"patient", "consumer"}:
            raise MetrcWorkbookContractError(
                "Sales Delivery requires SalesCustomerType Patient or Consumer as applicable to the state."
            )
        expected = 3 if operation == "sales_delivery_create" else 2
        if len(_list(payload, "transactions")) != expected:
            raise MetrcWorkbookContractError(
                f"{'Step 1' if expected == 3 else 'Step 2'} requires exactly {expected} delivery transactions."
            )
    if operation == "sales_delivery_complete":
        if len(_list(payload, "accepted_packages")) != 1 or len(_list(payload, "returned_packages")) != 1:
            raise MetrcWorkbookContractError(
                "Sales Delivery Step 3 requires exactly 1 AcceptedPackage and exactly 1 ReturnedPackage."
            )


def _first_source(evidence: dict[str, Any]) -> dict[str, Any] | None:
    readback = evidence.get("readback")
    if not isinstance(readback, dict):
        return None
    for record in readback.get("records") or []:
        if not isinstance(record, dict):
            continue
        source = record.get("source")
        if isinstance(source, dict):
            return source
    return None


def _field(source: dict[str, Any] | None, *names: str) -> Any:
    if not source:
        return None
    for name in names:
        if name not in source or source[name] is None:
            continue
        value = source[name]
        if isinstance(value, dict):
            for nested in ("Name", "name", "Label", "label", "Id", "id"):
                if value.get(nested) is not None:
                    return value[nested]
        return value
    return None


def _same_text(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def verify_workbook_evidence(operation_type: str, payload: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Require workbook business-field readback before a runner result can pass."""

    if not evidence.get("passed"):
        return evidence
    operation = str(operation_type or "").strip().casefold()
    source = _first_source(evidence)
    differences: list[dict[str, Any]] = []

    if operation == "location_update":
        actual = _field(source, "Name", "name")
        if actual is None or not _same_text(actual, payload.get("name")):
            differences.append({"field": "Name", "expected": payload.get("name"), "actual": actual})
    elif operation == "strain_update":
        for key, provider_key in (("indica_percentage", "IndicaPercentage"), ("sativa_percentage", "SativaPercentage")):
            actual = _field(source, provider_key)
            try:
                matched = float(actual) == float(payload.get(key))
            except (TypeError, ValueError):
                matched = False
            if not matched:
                differences.append({"field": provider_key, "expected": payload.get(key), "actual": actual})
    elif operation == "item_update":
        actual = _field(source, "UnitOfMeasure", "UnitOfMeasureName")
        if actual is None or not _same_text(actual, payload.get("unit_of_measure")):
            differences.append({"field": "UnitOfMeasure", "expected": payload.get("unit_of_measure"), "actual": actual})
    elif operation == "package_item":
        actual = _field(source, "Item", "ItemName")
        if actual is None or not _same_text(actual, payload.get("item")):
            differences.append({"field": "Item", "expected": payload.get("item"), "actual": actual})
    elif operation == "package_adjust":
        actual = _field(source, "Quantity", "CurrentQuantity")
        try:
            matched = abs(float(actual)) <= 1e-9
        except (TypeError, ValueError):
            matched = False
        if not matched:
            differences.append({"field": "Quantity", "expected": 0, "actual": actual})
    elif operation in {"package_finish", "package_unfinish"}:
        expected = operation == "package_finish"
        explicit = _field(source, "IsFinished", "Finished", "IsComplete", "Completed")
        finish_date = _field(source, "FinishedDate", "FinishDate", "CompletedDate", "CompletedAt")
        if explicit is not None:
            token = str(explicit).strip().casefold()
            actual_bool = token in {"true", "1", "yes", "finished", "complete", "completed"}
            matched = actual_bool is expected
            actual: Any = actual_bool
        else:
            actual = finish_date
            matched = bool(str(finish_date or "").strip()) if expected else not bool(str(finish_date or "").strip())
        if not matched:
            differences.append({"field": "Finished", "expected": expected, "actual": actual})
    elif operation in {"sales_delivery_create", "sales_delivery_update"}:
        expected_count = 3 if operation == "sales_delivery_create" else 2
        transactions = source.get("Transactions") if isinstance(source, dict) else None
        actual_count = len(transactions) if isinstance(transactions, list) else None
        if actual_count != expected_count:
            differences.append({"field": "Transactions", "expected_count": expected_count, "actual_count": actual_count})
        customer = _field(source, "SalesCustomerType")
        if customer is None or not _same_text(customer, payload.get("sales_customer_type")):
            differences.append({"field": "SalesCustomerType", "expected": payload.get("sales_customer_type"), "actual": customer})
    elif operation == "sales_delivery_complete":
        completed = _field(source, "IsComplete", "Completed", "CompletedDate", "ActualArrivalDateTime")
        if completed in (None, "", False):
            differences.append({"field": "Completed", "expected": True, "actual": completed})

    if differences:
        result = dict(evidence)
        result.update({
            "passed": False,
            "stage": "workbook_readback",
            "workbook_readback_verified": False,
            "workbook_differences": differences,
            "message": "Provider returned HTTP 200, but the literal workbook-required business change was not verified by readback.",
        })
        return result
    result = dict(evidence)
    result["workbook_readback_verified"] = True
    return result


def _response_payload(response: Any) -> Any:
    if not getattr(response, "content", b""):
        return None
    try:
        return response.json()
    except ValueError:
        return {"message": str(getattr(response, "text", ""))[:1000]}


def _ids(value: Any) -> list[str]:
    found: list[str] = []
    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, nested in node.items():
                if str(key).casefold() in {"id", "ids", "harvestid", "harvestids"}:
                    if isinstance(nested, list):
                        for item in nested:
                            token = str(item or "").strip()
                            if token and token not in found:
                                found.append(token)
                    else:
                        token = str(nested or "").strip()
                        if token and token not in found:
                            found.append(token)
                elif isinstance(nested, (dict, list)):
                    visit(nested)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(value)
    return found


def execute_two_plant_harvest_evaluation_action(
    *,
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
    """Execute Plants Step 6 exactly: two distinct plants into one named/date harvest."""

    validate_workbook_payload("plant_harvest", payload)
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or str(environment).casefold() != "sandbox":
        raise MetrcWorkbookContractError("Two-plant harvest evaluation is restricted to the MA sandbox.")
    license_number = str(license_number or "").strip()
    integrator_api_key = str(integrator_api_key or "").strip()
    user_api_key = str(user_api_key or "").strip()
    if not license_number or not integrator_api_key or not user_api_key or integrator_api_key == user_api_key:
        raise MetrcWorkbookContractError("Distinct existing vendor/user credentials and an exact license are required.")

    harvest_name = str(payload["harvest_name"]).strip()
    actual_date = str(payload["actual_date"]).strip()
    rows: list[dict[str, Any]] = []
    plant_context: list[dict[str, str]] = []
    for plant in payload["plants"]:
        plant_payload = dict(plant)
        plant_payload["plant"] = str(plant.get("plant") or plant.get("label") or "").strip()
        plant_payload["harvest_name"] = harvest_name
        plant_payload["actual_date"] = actual_date
        for shared in ("drying_location", "drying_sublocation", "unit_of_weight", "weight"):
            if plant_payload.get(shared) in (None, "") and payload.get(shared) not in (None, ""):
                plant_payload[shared] = payload[shared]
        rows.extend(build_lifecycle_evaluation_payload("plant_harvest", plant_payload))
        plant_context.append({"id": str(plant["id"]).strip(), "label": plant_payload["plant"]})

    response = (request_fn or requests.request)(
        "PUT",
        f"{base_url.rstrip('/')}/plants/v2/harvest",
        auth=(integrator_api_key, user_api_key),
        params={"licenseNumber": license_number},
        json=rows,
        timeout=timeout_seconds,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    http_status = int(getattr(response, "status_code", 0) or 0)
    response_payload = _response_payload(response)
    request_evidence = {
        "method": "PUT",
        "path": "plants/v2/harvest",
        "query": {"licenseNumber": license_number},
        "body": rows,
    }
    if http_status != 200:
        return {
            "passed": False,
            "stage": "write",
            "operation_type": "plant_harvest",
            "state": "MA",
            "environment": "sandbox",
            "license_number": license_number,
            "http_status": http_status,
            "request": request_evidence,
            "response": response_payload,
            "message": f"Metrc returned HTTP {http_status}; Plants Step 6 requires HTTP 200.",
        }

    harvest_ids = _ids(response_payload)
    if not harvest_ids:
        return {
            "passed": False,
            "stage": "readback_identity",
            "operation_type": "plant_harvest",
            "state": "MA",
            "environment": "sandbox",
            "license_number": license_number,
            "http_status": 200,
            "request": request_evidence,
            "response": response_payload,
            "message": "Metrc accepted the two-plant harvest, but no harvest identity was returned for exact verification.",
        }
    unique_ids = list(dict.fromkeys(harvest_ids))
    if len(unique_ids) != 1:
        return {
            "passed": False,
            "stage": "workbook_readback",
            "operation_type": "plant_harvest",
            "state": "MA",
            "environment": "sandbox",
            "license_number": license_number,
            "http_status": 200,
            "request": request_evidence,
            "response": response_payload,
            "provider_ids": unique_ids,
            "message": "Plants Step 6 must place both remaining plants in the same harvest; multiple harvest IDs were returned.",
        }
    harvest_id = unique_ids[0]

    fetch = readback_fn or fetch_metrc_resource
    harvest_readback = fetch(
        state="MA", user_api_key=user_api_key, integrator_api_key=integrator_api_key,
        resource="harvests_by_id", environment="sandbox", license_number=license_number,
        path_parameters={"id": harvest_id}, timeout_seconds=timeout_seconds,
    )
    harvest_source = None
    for record in (harvest_readback.get("records") or []) if isinstance(harvest_readback, dict) else []:
        if isinstance(record, dict) and isinstance(record.get("source"), dict):
            harvest_source = record["source"]
            break
    observed_name = _field(harvest_source, "Name", "HarvestName")
    harvest_ok = bool(harvest_readback.get("ok")) and observed_name is not None and _same_text(observed_name, harvest_name)

    plant_verification: list[dict[str, Any]] = []
    for plant in plant_context:
        readback = fetch(
            state="MA", user_api_key=user_api_key, integrator_api_key=integrator_api_key,
            resource="plants_by_id", environment="sandbox", license_number=license_number,
            path_parameters={"id": plant["id"]}, timeout_seconds=timeout_seconds,
        )
        checked = verify_plant_harvested(
            readback=readback,
            plant_provider_id=plant["id"],
            harvest_provider_id=harvest_id,
            harvest_name=harvest_name,
        )
        plant_verification.append({"plant_id": plant["id"], "label": plant["label"], **checked})

    passed = harvest_ok and all(row.get("matched") is True for row in plant_verification)
    return {
        "passed": passed,
        "stage": "complete" if passed else "workbook_readback",
        "operation_type": "plant_harvest",
        "state": "MA",
        "environment": "sandbox",
        "license_number": license_number,
        "http_status": 200,
        "provider_id": harvest_id,
        "request": request_evidence,
        "response": response_payload,
        "readback": harvest_readback,
        "plant_readback": plant_verification,
        "workbook_readback_verified": passed,
        "message": (
            "HTTP 200 plus exact readback verified both remaining plants in the same named harvest."
            if passed else
            "HTTP 200 was returned, but Plants Step 6 was not fully verified for both source plants and one shared harvest."
        ),
    }
