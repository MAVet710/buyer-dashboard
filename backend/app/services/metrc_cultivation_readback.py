from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _records(readback: Any) -> list[dict[str, Any]]:
    if not isinstance(readback, dict):
        return []
    return [dict(row) for row in readback.get("records") or [] if isinstance(row, dict)]


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return dict(value) if isinstance(value, dict) else {}


def _provider_id(record: dict[str, Any]) -> str:
    source = _source(record)
    value = record.get("provider_id") or source.get("Id") or source.get("id")
    return str(value or "").strip()


def _label(record: dict[str, Any]) -> str:
    source = _source(record)
    value = record.get("label") or source.get("Label") or source.get("Tag") or source.get("PlantLabel")
    return str(value or "").strip()


def _lookup(source: dict[str, Any], aliases: tuple[str, ...]) -> tuple[bool, Any]:
    for alias in aliases:
        if alias in source:
            value = source[alias]
            if isinstance(value, dict):
                for key in ("Name", "name", "Label", "label", "Value", "value"):
                    if key in value:
                        return True, value[key]
            return True, value
    return False, None


def _normalized(value: Any, *, date_like: bool = False) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10] if date_like else value.isoformat()
    text = str(value).strip()
    if date_like and text:
        return text[:10]
    try:
        return float(text)
    except (TypeError, ValueError):
        return text.casefold()


def _compare_fields(
    *,
    request_row: dict[str, Any],
    source: dict[str, Any],
    field_aliases: dict[str, tuple[str, ...]],
    date_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    dates = date_fields or set()
    for field, aliases in field_aliases.items():
        if field not in request_row:
            continue
        found, actual = _lookup(source, aliases)
        expected = request_row.get(field)
        if not found:
            differences.append({"field": field, "expected": expected, "actual": None, "reason": "missing_from_readback"})
            continue
        if _normalized(expected, date_like=field in dates) != _normalized(actual, date_like=field in dates):
            differences.append({"field": field, "expected": expected, "actual": actual, "reason": "value_mismatch"})
    return differences


def provider_ids_from_response(value: Any) -> list[str]:
    """Return stable unique provider IDs from a Metrc v2 mutation response."""

    found: list[str] = []

    def add(raw: Any) -> None:
        if raw is None or isinstance(raw, bool):
            return
        token = str(raw).strip()
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
        if isinstance(node, (str, int, float)):
            add(node)

    visit(value)
    return found


def verify_plant_batch_creation(
    *,
    provider_request_body: Any,
    readback: Any,
    provider_id: str,
) -> dict[str, Any]:
    body = [dict(row) for row in provider_request_body or [] if isinstance(row, dict)]
    records = _records(readback)
    expected_id = str(provider_id or "").strip()
    if len(body) != 1:
        return {"matched": False, "differences": [{"field": "body", "reason": "expected_one_row"}], "record": None}
    record = next((row for row in records if _provider_id(row) == expected_id), None)
    if record is None:
        return {"matched": False, "differences": [{"field": "Id", "expected": expected_id, "actual": None, "reason": "provider_id_not_found"}], "record": None}

    source = _source(record)
    differences = _compare_fields(
        request_row=body[0],
        source=source,
        field_aliases={
            "Name": ("Name", "PlantBatchName"),
            "Type": ("Type", "PlantBatchType", "PlantBatchTypeName"),
            "Count": ("Count", "UntrackedCount", "PlantCount"),
            "Strain": ("Strain", "StrainName"),
            "Location": ("Location", "LocationName"),
            "ActualDate": ("ActualDate", "PlantedDate", "PlantingDate"),
        },
        date_fields={"ActualDate"},
    )
    return {"matched": not differences, "differences": differences, "record": record}


def verify_plant_location(
    *,
    provider_request_body: Any,
    readback: Any,
    provider_id: str,
) -> dict[str, Any]:
    body = [dict(row) for row in provider_request_body or [] if isinstance(row, dict)]
    records = _records(readback)
    expected_id = str(provider_id or "").strip()
    if len(body) != 1:
        return {"matched": False, "differences": [{"field": "body", "reason": "expected_one_row"}], "record": None}
    record = next((row for row in records if _provider_id(row) == expected_id), None)
    if record is None:
        return {"matched": False, "differences": [{"field": "Id", "expected": expected_id, "actual": None, "reason": "provider_id_not_found"}], "record": None}

    source = _source(record)
    differences = _compare_fields(
        request_row=body[0],
        source=source,
        field_aliases={
            "Location": ("Location", "LocationName"),
            "Label": ("Label", "PlantLabel", "Tag"),
            "ActualDate": ("ActualDate", "MoveDate", "LastModified"),
        },
        # Metrc does not guarantee that the movement date is echoed under the
        # same field on every jurisdiction read model. Location identity is the
        # required post-state; Label is compared when it was sent.
        date_fields=set(),
    )
    # ActualDate is audit context for the mutation, not a stable plant snapshot
    # field. Do not require an alias that can legitimately be absent.
    differences = [row for row in differences if row.get("field") != "ActualDate"]
    return {"matched": not differences, "differences": differences, "record": record}


def verify_vegetative_plants(
    *,
    readbacks: list[dict[str, Any]],
    expected_count: int,
    expected_location: str,
    expected_strain: str,
) -> dict[str, Any]:
    expected = int(expected_count or 0)
    flattened: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    for index, readback in enumerate(readbacks):
        if not isinstance(readback, dict) or not readback.get("ok"):
            differences.append({"field": "readback", "index": index, "reason": "provider_read_failed"})
            continue
        rows = _records(readback)
        if len(rows) != 1:
            differences.append({"field": "readback", "index": index, "reason": "expected_exactly_one_plant"})
            continue
        flattened.append(rows[0])

    if len(flattened) != expected:
        differences.append({"field": "Count", "expected": expected, "actual": len(flattened), "reason": "plant_count_mismatch"})

    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    plants: list[dict[str, Any]] = []
    for record in flattened:
        source = _source(record)
        provider_id = _provider_id(record)
        label = _label(record)
        if not provider_id or provider_id in seen_ids:
            differences.append({"field": "Id", "actual": provider_id or None, "reason": "missing_or_duplicate_provider_id"})
        else:
            seen_ids.add(provider_id)
        if not label or label.casefold() in seen_labels:
            differences.append({"field": "Label", "actual": label or None, "reason": "missing_or_duplicate_plant_label"})
        else:
            seen_labels.add(label.casefold())

        found_phase, actual_phase = _lookup(source, ("GrowthPhase", "GrowthPhaseName", "Phase"))
        if not found_phase or _normalized(actual_phase) != _normalized("Vegetative"):
            differences.append({"field": "GrowthPhase", "provider_id": provider_id, "expected": "Vegetative", "actual": actual_phase, "reason": "value_mismatch" if found_phase else "missing_from_readback"})

        found_location, actual_location = _lookup(source, ("Location", "LocationName"))
        if not found_location or _normalized(actual_location) != _normalized(expected_location):
            differences.append({"field": "Location", "provider_id": provider_id, "expected": expected_location, "actual": actual_location, "reason": "value_mismatch" if found_location else "missing_from_readback"})

        if expected_strain:
            found_strain, actual_strain = _lookup(source, ("Strain", "StrainName"))
            if not found_strain or _normalized(actual_strain) != _normalized(expected_strain):
                differences.append({"field": "Strain", "provider_id": provider_id, "expected": expected_strain, "actual": actual_strain, "reason": "value_mismatch" if found_strain else "missing_from_readback"})

        plants.append({"provider_id": provider_id, "label": label, "source": source})

    return {
        "matched": not differences and len(plants) == expected,
        "differences": differences,
        "plants": sorted(plants, key=lambda row: str(row.get("label") or "").casefold()),
    }
