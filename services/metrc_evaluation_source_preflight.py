"""Read-only source-state checks required by literal MA evaluation wording.

These checks run before a mutation. They never create provider data and never
change credentials. Their purpose is to prevent a syntactically valid Metrc
request from violating a workbook instruction such as "Flowering Plant",
"different location", "remaining weight", or "adjust ... to 0".
"""

from __future__ import annotations

from math import isclose
from typing import Any, Callable

from services.metrc_client import fetch_metrc_resource
from services.metrc_evaluation_workbook_contract import MetrcWorkbookContractError


def _source(read: Any, provider_id: str) -> dict[str, Any] | None:
    if not isinstance(read, dict) or not read.get("ok"):
        return None
    wanted = str(provider_id or "").strip()
    for record in read.get("records") or []:
        if not isinstance(record, dict):
            continue
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        candidate = str(record.get("provider_id") or source.get("Id") or source.get("id") or "").strip()
        if candidate == wanted:
            return dict(source)
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


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_text(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _fetch(
    fetch_fn: Callable[..., dict[str, Any]],
    *,
    resource: str,
    provider_id: str,
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    return fetch_fn(
        state="MA",
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource=resource,
        environment="sandbox",
        license_number=license_number,
        path_parameters={"id": provider_id},
        timeout_seconds=timeout_seconds,
    )


def preflight_workbook_source_state(
    *,
    operation_type: str,
    payload: dict[str, Any],
    license_number: str,
    integrator_api_key: str,
    user_api_key: str,
    timeout_seconds: int = 30,
    fetch_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return bounded read-only source evidence or raise before dispatch."""

    operation = str(operation_type or "").strip().casefold()
    fetch = fetch_fn or fetch_metrc_resource

    if operation == "plant_location":
        provider_id = str(payload.get("id") or "").strip()
        read = _fetch(
            fetch, resource="plants_by_id", provider_id=provider_id,
            license_number=license_number, integrator_api_key=integrator_api_key,
            user_api_key=user_api_key, timeout_seconds=timeout_seconds,
        )
        source = _source(read, provider_id)
        if source is None:
            raise MetrcWorkbookContractError("Plants Step 1 requires a verifiable existing plant before location update.")
        phase = _field(source, "GrowthPhase", "Phase", "State", "Status")
        if phase is None or "flower" not in str(phase).casefold():
            raise MetrcWorkbookContractError(
                f"Plants Step 1 requires a Flowering Plant; provider readback reported {phase!r}."
            )
        current_location = _field(
            source,
            "LocationName", "Location", "CurrentLocationName", "CurrentLocation",
        )
        target_location = str(payload.get("location") or "").strip()
        if current_location is not None and _same_text(current_location, target_location):
            raise MetrcWorkbookContractError(
                "Plants Step 1 requires moving the Flowering Plant to a different location."
            )
        return {
            "verified": True,
            "operation_type": operation,
            "provider_id": provider_id,
            "growth_phase": phase,
            "current_location": current_location,
            "target_location": target_location,
        }

    if operation == "harvest_waste":
        provider_id = str(payload.get("id") or "").strip()
        read = _fetch(
            fetch, resource="harvests_by_id", provider_id=provider_id,
            license_number=license_number, integrator_api_key=integrator_api_key,
            user_api_key=user_api_key, timeout_seconds=timeout_seconds,
        )
        source = _source(read, provider_id)
        if source is None:
            raise MetrcWorkbookContractError("Harvest Step 2 requires the exact existing harvest from Plants Step 6.")
        current_weight = _number(_field(source, "CurrentWeight", "TotalWetWeight", "WetWeight", "Weight"))
        submitted_weight = _number(payload.get("waste_weight"))
        if current_weight is None:
            raise MetrcWorkbookContractError(
                "Harvest Step 2 cannot prove the remaining harvest weight from provider readback."
            )
        if submitted_weight is None or not isclose(submitted_weight, current_weight, abs_tol=0.01, rel_tol=0.0):
            raise MetrcWorkbookContractError(
                f"Harvest Step 2 must remove the remaining weight as waste; remaining={current_weight}, submitted={submitted_weight}."
            )
        provider_unit = _field(
            source,
            "CurrentWeightUnitOfMeasureName", "UnitOfWeight", "UnitOfWeightName", "WeightUnitOfMeasureName",
        )
        submitted_unit = str(payload.get("unit_of_weight") or "").strip()
        if provider_unit and submitted_unit and not _same_text(provider_unit, submitted_unit):
            raise MetrcWorkbookContractError(
                f"Harvest Step 2 waste unit does not match provider remaining-weight unit: {provider_unit!r}."
            )
        return {
            "verified": True,
            "operation_type": operation,
            "provider_id": provider_id,
            "remaining_weight": current_weight,
            "unit_of_weight": provider_unit or submitted_unit,
        }

    if operation in {"package_adjust", "package_finish", "package_unfinish"}:
        provider_id = str(payload.get("package_id") or "").strip()
        read = _fetch(
            fetch, resource="packages_by_id", provider_id=provider_id,
            license_number=license_number, integrator_api_key=integrator_api_key,
            user_api_key=user_api_key, timeout_seconds=timeout_seconds,
        )
        source = _source(read, provider_id)
        if source is None:
            raise MetrcWorkbookContractError("Package evaluation step requires the exact package created in Packages Step 1.")
        quantity = _number(_field(source, "Quantity", "CurrentQuantity"))
        unit = _field(source, "UnitOfMeasureName", "UnitOfMeasure", "Unit")
        finished_raw = _field(source, "IsFinished", "Finished")
        finished = str(finished_raw or "").strip().casefold() in {"true", "1", "yes", "finished"}

        if operation == "package_adjust":
            adjustment = _number(payload.get("quantity"))
            if quantity is None or adjustment is None:
                raise MetrcWorkbookContractError("Packages Step 3 requires current quantity and numeric adjustment evidence.")
            if not isclose(quantity + adjustment, 0.0, abs_tol=0.01, rel_tol=0.0):
                raise MetrcWorkbookContractError(
                    f"Packages Step 3 must adjust the package to 0; current={quantity}, adjustment={adjustment}."
                )
            submitted_unit = str(payload.get("unit_of_measure") or "").strip()
            if unit and submitted_unit and not _same_text(unit, submitted_unit):
                raise MetrcWorkbookContractError(
                    f"Packages Step 3 adjustment unit does not match provider package unit: {unit!r}."
                )
        elif operation == "package_finish":
            if quantity is None or not isclose(quantity, 0.0, abs_tol=0.01, rel_tol=0.0):
                raise MetrcWorkbookContractError(
                    f"Packages Step 4 requires the Step 3 package to be at 0 before finish; current={quantity}."
                )
        elif operation == "package_unfinish" and not finished:
            raise MetrcWorkbookContractError(
                "Packages Step 5 requires the package finished in Step 4 to be finished before unfinish."
            )
        return {
            "verified": True,
            "operation_type": operation,
            "provider_id": provider_id,
            "current_quantity": quantity,
            "unit_of_measure": unit,
            "is_finished": finished,
        }

    if operation in {"sales_delivery_update", "sales_delivery_complete"}:
        provider_id = str(payload.get("id") or "").strip()
        read = _fetch(
            fetch, resource="sales_deliveries_by_id", provider_id=provider_id,
            license_number=license_number, integrator_api_key=integrator_api_key,
            user_api_key=user_api_key, timeout_seconds=timeout_seconds,
        )
        source = _source(read, provider_id)
        if source is None:
            raise MetrcWorkbookContractError(
                "Sales Delivery Step 2/3 requires the exact delivery created in Step 1."
            )
        transactions = source.get("Transactions") if isinstance(source.get("Transactions"), list) else None
        expected_before = 3 if operation == "sales_delivery_update" else 2
        if transactions is not None and len(transactions) != expected_before:
            raise MetrcWorkbookContractError(
                f"{operation} expected {expected_before} transactions before the action; provider readback has {len(transactions)}."
            )
        return {
            "verified": True,
            "operation_type": operation,
            "provider_id": provider_id,
            "transaction_count": len(transactions) if transactions is not None else None,
        }

    return {"verified": True, "operation_type": operation, "check": "no additional source-state rule"}
