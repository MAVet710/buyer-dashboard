"""Literal Generic Evaluation 10.2025 execution contract for Massachusetts.

The workbook is the evaluation source of truth.  This module deliberately keeps
provider API validity separate from evaluation validity: a request may be legal
Metrc v2 JSON and still fail the workbook if it targets the wrong facility,
uses the wrong prior object, omits an instructed change, or cannot be verified.

Nothing in this module provisions or rotates credentials.
"""

from __future__ import annotations

from math import isclose
from typing import Any, Callable

import requests

from modules.regulatory.registry import resolve_metrc_base_url
from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_lifecycle import build_lifecycle_evaluation_payload
from services.metrc_facility_capabilities import (
    provider_boolean_capabilities,
    provider_facility_license,
)


class MetrcWorkbookContractError(RuntimeError):
    """Raised before dispatch when the literal workbook task is not satisfied."""


# Exact dependency prose from the Permissions worksheet.  This is retained for
# access-request/submission reasoning; it does NOT multiply the 46 action rows.
WORKBOOK_PERMISSION_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "grow": (
        "Locations", "Strains", "Plant Batches", "Plants", "Harvests", "Items",
        "Packages", "GET Transfers / Wholesale",
    ),
    "processor": ("Strains", "Items", "Packages", "GET Transfers / Wholesale"),
    "labs": ("Strains", "Packages", "Labs", "GET Transfers / Wholesale"),
    "sales": (
        "Strains", "Packages", "Items", "Sales", "Sales Deliveries",
        "GET Transfers / Wholesale",
    ),
}
WORKBOOK_OPTIONAL_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "grow": ("Transfer Templates",),
    "processor": ("Transfer Templates",),
    "labs": ("Items", "Transfer Templates"),
    "sales": ("Transfer Templates",),
}

_GROW_OPERATIONS = frozenset({
    "location_create", "location_update", "location_get",
    "strain_create", "strain_update", "strain_get",
    "item_create", "item_update", "item_get",
    "plant_batch_plantings", "plant_batch_packages", "plant_batch_growthphase", "plant_batch_delete",
    "plant_location", "plant_plantings", "plant_plantbatch_packages", "plant_delete", "plant_manicure", "plant_harvest",
    "harvest_packages", "harvest_waste", "harvest_finish", "harvest_unfinish",
    "package_create", "package_item", "package_adjust", "package_finish", "package_unfinish",
    "transfer_incoming", "transfer_outgoing", "transfer_rejected", "transfer_deliveries",
    "transfer_delivery_packages", "transfer_delivery_packages_wholesale",
    "transfer_template_create", "transfer_template_list", "transfer_template_deliveries", "transfer_template_update",
})
_LAB_OPERATIONS = frozenset({"lab_test_record"})
_SALES_OPERATIONS = frozenset({
    "sales_receipt_create", "sales_receipt_update", "sales_receipt_delete",
    "sales_delivery_create", "sales_delivery_update", "sales_delivery_complete",
})

# Dedicated generic sandbox facilities are preferred over broad multi-license
# types.  An explicit license override always wins after validation.
_DEFAULT_FACILITY_NAMES: dict[str, tuple[str, ...]] = {
    "grow": ("Sandbox Marijuana Cultivator", "Sandbox Medical Marijuana Cultivator"),
    "labs": ("Sandbox Independent Testing Laboratory", "Sandbox Medical Independent Testing Laboratory", "Sandbox Standards Laboratory"),
    "sales": ("Sandbox Marijuana Retailer", "Sandbox Medical Marijuana Retailer"),
}


def _source(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    nested = record.get("source")
    return nested if isinstance(nested, dict) else record


def _facility_name(record: Any) -> str:
    row = _source(record)
    for key in ("Name", "name", "FacilityName", "facilityName"):
        token = str(row.get(key) or "").strip()
        if token:
            return token
    return ""


def _role_for_operation(operation_type: str) -> str:
    operation = str(operation_type or "").strip().casefold()
    if operation in _LAB_OPERATIONS:
        return "labs"
    if operation in _SALES_OPERATIONS:
        return "sales"
    if operation in _GROW_OPERATIONS:
        return "grow"
    raise MetrcWorkbookContractError(f"No workbook facility role is registered for {operation!r}.")


def _cap_true(capabilities: dict[str, bool], *names: str) -> bool:
    return any(capabilities.get(name) is True for name in names)


def _operation_capability_ok(operation_type: str, record: Any) -> bool:
    """Use only direct provider capability evidence that clearly matches a task family.

    The absence of a named capability is not treated as proof that an unrelated
    master-data/transfer action is unauthorized.  Scoped HTTP 401 remains the
    workbook's permission signal for those actions.
    """

    operation = str(operation_type or "").strip().casefold()
    caps = provider_boolean_capabilities(record)
    if operation.startswith("plant_") or operation.startswith("plant_batch_") or operation.startswith("harvest_"):
        return caps.get("CanGrowPlants") is True
    if operation == "lab_test_record":
        return caps.get("CanTestPackages") is True
    if operation.startswith("sales_receipt_"):
        return _cap_true(caps, "CanSellToConsumers", "CanSellToPatients", "CanSellToCaregivers", "CanSellToExternalPatients")
    if operation.startswith("sales_delivery_"):
        return _cap_true(caps, "CanDeliverSalesToConsumers", "CanDeliverSalesToPatients", "CanDeliverSalesToCaregivers")
    if operation == "package_create" and "CanCreateDerivedPackages" in caps:
        return caps.get("CanCreateDerivedPackages") is True
    return True


def select_facility_for_operation(
    *,
    operation_type: str,
    facility_records: list[dict[str, Any]],
    explicit_license: str = "",
) -> dict[str, Any]:
    """Resolve one exact facility from the authenticated Facilities response.

    The old evaluation workflow forced one environment license onto every task.
    That is not supported by the workbook.  An explicit license can be supplied
    for reproducibility; otherwise the dedicated generic sandbox facility for
    the task family is selected deterministically.
    """

    operation = str(operation_type or "").strip().casefold()
    wanted = str(explicit_license or "").strip()
    if wanted:
        matches = [row for row in facility_records if provider_facility_license(row) == wanted]
        if len(matches) != 1:
            raise MetrcWorkbookContractError(
                f"Expected exactly one GET /facilities/v2 record for {wanted}; observed {len(matches)}."
            )
        selected = matches[0]
        if not _operation_capability_ok(operation, selected):
            raise MetrcWorkbookContractError(
                f"Facility {wanted} does not expose the provider capability profile required for {operation}."
            )
        return {
            "license_number": wanted,
            "facility_name": _facility_name(selected),
            "selection": "explicit",
            "capabilities": provider_boolean_capabilities(selected),
        }

    role = _role_for_operation(operation)
    rows_by_name = {_facility_name(row): row for row in facility_records if _facility_name(row)}
    for name in _DEFAULT_FACILITY_NAMES[role]:
        row = rows_by_name.get(name)
        if row is None:
            continue
        if not _operation_capability_ok(operation, row):
            continue
        license_number = provider_facility_license(row)
        if license_number:
            return {
                "license_number": license_number,
                "facility_name": name,
                "selection": f"dedicated_{role}_facility",
                "capabilities": provider_boolean_capabilities(row),
            }
    raise MetrcWorkbookContractError(
        f"GET /facilities/v2 did not expose a dedicated {role} sandbox facility compatible with {operation}. "
        "Supply an explicit license only after confirming it in the authenticated Facilities response."
    )


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
    """Fail before dispatch when API-valid JSON misses a literal workbook task."""

    operation = str(operation_type or "").strip().casefold()
    if not isinstance(payload, dict):
        raise MetrcWorkbookContractError("Workbook evaluation payload must be one JSON object.")

    if operation == "location_update" and not str(payload.get("name") or "").strip():
        raise MetrcWorkbookContractError("Locations Step 2 must update the location name.")
    if operation == "strain_update":
        if payload.get("indica_percentage") in (None, "") or payload.get("sativa_percentage") in (None, ""):
            raise MetrcWorkbookContractError("Strains Step 2 must change both Indica and Sativa Percentage.")
    if operation == "item_update" and not str(payload.get("unit_of_measure") or "").strip():
        raise MetrcWorkbookContractError("Items Step 2 must change the Unit of Measure Type.")

    exact_counts = {
        "plant_batch_plantings": ("count", 6, "Plant Batches Step 1 must create a new plant batch containing 6 plants."),
        "plant_batch_packages": ("count", 3, "Plant Batches Step 2 must package 3 clones from the Step 1 batch."),
        "plant_batch_growthphase": ("count", 2, "Plant Batches Step 3 must change 2 plants to Vegetative."),
        "plant_batch_delete": ("count", 1, "Plant Batches Step 4 must destroy 1 plant."),
        "plant_delete": ("count", 1, "Plants Step 4 must destroy one plant."),
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
            raise MetrcWorkbookContractError("Plants Step 6 must use the 2 remaining plants to create a harvest.")
        harvest_name = str(payload.get("harvest_name") or "").strip()
        actual_date = str(payload.get("actual_date") or "").strip()
        if not harvest_name or not actual_date:
            raise MetrcWorkbookContractError(
                "Plants Step 6 requires one exact HarvestName and one calendar-day ActualDate for both plants."
            )
        ids: set[str] = set()
        labels: set[str] = set()
        for index, row in enumerate(plants, start=1):
            plant_id = str(row.get("id") or "").strip()
            label = str(row.get("plant") or row.get("label") or "").strip()
            if not plant_id or not label:
                raise MetrcWorkbookContractError(
                    f"Plants Step 6 plant {index} requires provider id and plant label for exact verification."
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
        if target is None or not isclose(target, 0.0, abs_tol=1e-9, rel_tol=0.0):
            raise MetrcWorkbookContractError(
                "Packages Step 3 must declare expected_final_quantity=0 so the final provider quantity can be proven."
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
                f"Sales Delivery {'Step 1' if expected == 3 else 'Step 2'} requires exactly {expected} transactions."
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
        if isinstance(record, dict) and isinstance(record.get("source"), dict):
            return record["source"]
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
    """Require the business change named by the workbook, not provider ID alone."""

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
            matched = isclose(float(actual), 0.0, abs_tol=1e-9, rel_tol=0.0)
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
            "message": "HTTP 200 was returned, but the literal workbook-required change was not verified by provider readback.",
        })
        return result
    result = dict(evidence)
    result["workbook_readback_verified"] = True
    return result


def _read_source(readback: Any, provider_id: str) -> dict[str, Any] | None:
    if not isinstance(readback, dict) or not readback.get("ok"):
        return None
    wanted = str(provider_id or "").strip()
    for record in readback.get("records") or []:
        if not isinstance(record, dict):
            continue
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        record_id = str(record.get("provider_id") or source.get("Id") or source.get("id") or "").strip()
        if record_id == wanted:
            return dict(source)
    return None


def _verify_source_plant_harvested(readback: Any, plant_id: str, harvest_id: str, harvest_name: str) -> bool:
    if isinstance(readback, dict) and int(readback.get("http_status") or 0) in {404, 410}:
        return True
    source = _read_source(readback, plant_id)
    if source is None:
        return False
    provider_harvest_id = _field(source, "HarvestId", "CurrentHarvestId")
    provider_harvest_name = _field(source, "HarvestName", "CurrentHarvestName")
    phase = _field(source, "GrowthPhase", "Phase", "State", "Status")
    harvested = _field(source, "IsHarvested", "Harvested")
    if provider_harvest_id is not None and _same_text(provider_harvest_id, harvest_id):
        return True
    if provider_harvest_name is not None and _same_text(provider_harvest_name, harvest_name):
        return True
    if phase is not None and "harvest" in str(phase).casefold():
        return True
    return str(harvested or "").strip().casefold() in {"true", "1", "yes"}


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
                    values = nested if isinstance(nested, list) else [nested]
                    for item in values:
                        token = str(item or "").strip()
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
    """Execute Plants Step 6 exactly: two plants, one harvest name, one day."""

    validate_workbook_payload("plant_harvest", payload)
    base_url, state_code = resolve_metrc_base_url(state, environment=environment)
    if state_code != "MA" or str(environment).casefold() != "sandbox":
        raise MetrcWorkbookContractError("Plants Step 6 execution is restricted to the MA sandbox.")
    license_number = str(license_number or "").strip()
    vendor_key = str(integrator_api_key or "").strip()
    user_key = str(user_api_key or "").strip()
    if not license_number or not vendor_key or not user_key or vendor_key == user_key:
        raise MetrcWorkbookContractError("Distinct existing vendor/user credentials and an exact facility license are required.")

    harvest_name = str(payload["harvest_name"]).strip()
    actual_date = str(payload["actual_date"]).strip()
    rows: list[dict[str, Any]] = []
    plants: list[dict[str, str]] = []
    for plant in payload["plants"]:
        plant_payload = dict(plant)
        plant_payload["plant"] = str(plant.get("plant") or plant.get("label") or "").strip()
        plant_payload["harvest_name"] = harvest_name
        plant_payload["actual_date"] = actual_date
        for shared in ("drying_location", "drying_sublocation", "unit_of_weight", "weight"):
            if plant_payload.get(shared) in (None, "") and payload.get(shared) not in (None, ""):
                plant_payload[shared] = payload[shared]
        rows.extend(build_lifecycle_evaluation_payload("plant_harvest", plant_payload))
        plants.append({"id": str(plant["id"]).strip(), "label": plant_payload["plant"]})

    try:
        response = (request_fn or requests.request)(
            "PUT",
            f"{base_url.rstrip('/')}/plants/v2/harvest",
            auth=(vendor_key, user_key),
            params={"licenseNumber": license_number},
            json=rows,
            timeout=timeout_seconds,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise MetrcWorkbookContractError(f"Plants Step 6 request failed before evidence capture: {type(exc).__name__}.") from exc

    http_status = int(getattr(response, "status_code", 0) or 0)
    provider_response = _response_payload(response)
    request_evidence = {"method": "PUT", "path": "plants/v2/harvest", "query": {"licenseNumber": license_number}, "body": rows}
    if http_status != 200:
        return {
            "passed": False, "stage": "write", "operation_type": "plant_harvest", "state": "MA",
            "environment": "sandbox", "license_number": license_number, "http_status": http_status,
            "request": request_evidence, "response": provider_response,
            "message": f"Metrc returned HTTP {http_status}; Plants Step 6 requires HTTP 200.",
        }

    harvest_ids = list(dict.fromkeys(_ids(provider_response)))
    if len(harvest_ids) != 1:
        return {
            "passed": False, "stage": "readback_identity", "operation_type": "plant_harvest", "state": "MA",
            "environment": "sandbox", "license_number": license_number, "http_status": 200,
            "request": request_evidence, "response": provider_response, "provider_ids": harvest_ids,
            "message": "Plants Step 6 could not prove one shared harvest identity for both plants.",
        }
    harvest_id = harvest_ids[0]
    fetch = readback_fn or fetch_metrc_resource
    harvest_readback = fetch(
        state="MA", user_api_key=user_key, integrator_api_key=vendor_key,
        resource="harvests_by_id", environment="sandbox", license_number=license_number,
        path_parameters={"id": harvest_id}, timeout_seconds=timeout_seconds,
    )
    harvest_source = _read_source(harvest_readback, harvest_id)
    observed_name = _field(harvest_source, "Name", "HarvestName")
    harvest_ok = observed_name is not None and _same_text(observed_name, harvest_name)

    plant_readback: list[dict[str, Any]] = []
    for plant in plants:
        readback = fetch(
            state="MA", user_api_key=user_key, integrator_api_key=vendor_key,
            resource="plants_by_id", environment="sandbox", license_number=license_number,
            path_parameters={"id": plant["id"]}, timeout_seconds=timeout_seconds,
        )
        matched = _verify_source_plant_harvested(readback, plant["id"], harvest_id, harvest_name)
        plant_readback.append({"plant_id": plant["id"], "label": plant["label"], "matched": matched})

    passed = harvest_ok and all(row["matched"] for row in plant_readback)
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
        "response": provider_response,
        "readback": harvest_readback,
        "plant_readback": plant_readback,
        "workbook_readback_verified": passed,
        "message": (
            "HTTP 200 plus readback verified both remaining plants in the same named harvest."
            if passed else
            "HTTP 200 was returned, but Plants Step 6 was not fully verified for both plants and one shared harvest."
        ),
    }
