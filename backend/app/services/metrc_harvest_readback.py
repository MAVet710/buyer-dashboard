from __future__ import annotations

from math import isclose
from typing import Any


def _source(readback: Any, provider_id: str) -> dict[str, Any] | None:
    if not isinstance(readback, dict) or not readback.get("ok"):
        return None
    wanted = str(provider_id or "").strip()
    for record in readback.get("records") or []:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("provider_id") or "").strip()
        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        source_id = str(source.get("Id") or source.get("id") or "").strip()
        if wanted and wanted in {record_id, source_id}:
            return dict(source)
    return None


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key not in source or source[key] is None:
            continue
        value = source[key]
        if isinstance(value, dict):
            for nested in ("Name", "name", "Label", "label", "Id", "id"):
                if nested in value and value[nested] is not None:
                    return value[nested]
        return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _same_text(left: Any, right: Any) -> bool:
    return _text(left).casefold() == _text(right).casefold()


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_number(left: Any, right: float, *, tolerance: float = 0.01) -> bool:
    value = _number(left)
    return value is not None and isclose(value, float(right), abs_tol=tolerance, rel_tol=0.0)


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    token = _text(value).casefold()
    if token in {"true", "yes", "y", "1", "finished", "complete", "completed"}:
        return True
    if token in {"false", "no", "n", "0", "active", "open", "unfinished"}:
        return False
    return None


def verify_harvest_state(
    *,
    readback: Any,
    provider_id: str,
    expected_name: str,
    expected_location: str,
    expected_weight_g: float,
) -> dict[str, Any]:
    """Require exact harvest identity plus name/location/current wet-weight state.

    Metrc source records have changed field spelling over time, so this accepts a
    bounded set of reviewed aliases but fails closed when the business field is
    absent instead of treating provider identity alone as verification.
    """

    source = _source(readback, provider_id)
    differences: list[dict[str, Any]] = []
    if source is None:
        return {"matched": False, "differences": [{"field": "Id", "expected": provider_id, "actual": None}], "source": None}

    actual_name = _first(source, "Name", "HarvestName", "name")
    if actual_name is None or not _same_text(actual_name, expected_name):
        differences.append({"field": "Name", "expected": expected_name, "actual": actual_name})

    actual_location = _first(
        source,
        "DryingLocationName",
        "DryingLocation",
        "LocationName",
        "Location",
        "CurrentLocationName",
    )
    if actual_location is None or not _same_text(actual_location, expected_location):
        differences.append({"field": "DryingLocation", "expected": expected_location, "actual": actual_location})

    actual_weight = _first(
        source,
        "CurrentWeight",
        "TotalWetWeight",
        "WetWeight",
        "Weight",
    )
    if actual_weight is None or not _same_number(actual_weight, expected_weight_g):
        differences.append({"field": "CurrentWeight", "expected": float(expected_weight_g), "actual": actual_weight})

    return {"matched": not differences, "differences": differences, "source": source}


def verify_plant_harvested(
    *,
    readback: Any,
    plant_provider_id: str,
    harvest_provider_id: str,
    harvest_name: str,
) -> dict[str, Any]:
    """Verify one source plant is actually attached to the intended harvest.

    A 404/410 is accepted because some Metrc environments stop exposing a plant
    by the active-plant by-ID resource once harvested. If it remains readable,
    an explicit harvest identity/name or harvested lifecycle state is required.
    """

    if isinstance(readback, dict) and int(readback.get("http_status") or 0) in {404, 410}:
        return {"matched": True, "mode": "source_absent", "source": None, "differences": []}

    source = _source(readback, plant_provider_id)
    if source is None:
        return {"matched": False, "mode": "unverified", "source": None, "differences": [{"field": "plant", "expected": plant_provider_id, "actual": None}]}

    actual_harvest_id = _first(source, "HarvestId", "CurrentHarvestId")
    actual_harvest_name = _first(source, "HarvestName", "CurrentHarvestName")
    phase = _first(source, "GrowthPhase", "Phase", "State", "Status")
    harvested_flag = _first(source, "IsHarvested", "Harvested")

    identity_match = (
        actual_harvest_id is not None and _same_text(actual_harvest_id, harvest_provider_id)
    ) or (
        actual_harvest_name is not None and _same_text(actual_harvest_name, harvest_name)
    )
    lifecycle_match = (
        phase is not None and "harvest" in _text(phase).casefold()
    ) or _bool(harvested_flag) is True

    if identity_match or lifecycle_match:
        return {"matched": True, "mode": "source_state", "source": source, "differences": []}
    return {
        "matched": False,
        "mode": "source_state",
        "source": source,
        "differences": [{
            "field": "harvest_assignment",
            "expected": {"harvest_id": harvest_provider_id, "harvest_name": harvest_name},
            "actual": {"harvest_id": actual_harvest_id, "harvest_name": actual_harvest_name, "phase": phase, "harvested": harvested_flag},
        }],
    }


def harvest_waste_weight(source: dict[str, Any] | None) -> float | None:
    if not source:
        return None
    return _number(_first(source, "TotalWasteWeight", "WasteWeight", "TotalWaste"))


def verify_harvest_waste(
    *,
    readback: Any,
    provider_id: str,
    baseline_waste_weight_g: float,
    submitted_waste_weight_g: float,
) -> dict[str, Any]:
    source = _source(readback, provider_id)
    actual = harvest_waste_weight(source)
    expected = float(baseline_waste_weight_g) + float(submitted_waste_weight_g)
    matched = actual is not None and _same_number(actual, expected)
    return {
        "matched": matched,
        "expected_waste_weight_g": expected,
        "actual_waste_weight_g": actual,
        "differences": [] if matched else [{"field": "TotalWasteWeight", "expected": expected, "actual": actual}],
        "source": source,
    }


def verify_harvest_finished(*, readback: Any, provider_id: str, expected_finished: bool) -> dict[str, Any]:
    source = _source(readback, provider_id)
    if source is None:
        return {"matched": False, "differences": [{"field": "Id", "expected": provider_id, "actual": None}], "source": None}

    explicit = _first(source, "IsFinished", "Finished", "IsComplete", "Completed")
    finish_date = _first(source, "FinishDate", "FinishedDate", "CompletedDate", "CompletedAt")
    explicit_bool = _bool(explicit)
    if explicit_bool is not None:
        matched = explicit_bool is expected_finished
        actual: Any = explicit_bool
    elif expected_finished:
        matched = bool(_text(finish_date))
        actual = finish_date
    else:
        matched = not bool(_text(finish_date))
        actual = finish_date

    return {
        "matched": matched,
        "differences": [] if matched else [{"field": "Finished", "expected": expected_finished, "actual": actual}],
        "source": source,
    }
