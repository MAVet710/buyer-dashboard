from __future__ import annotations

from math import isclose
from typing import Any


def _records(readback: Any) -> list[dict[str, Any]]:
    if not isinstance(readback, dict) or not readback.get("ok"):
        return []
    return [dict(row) for row in readback.get("records") or [] if isinstance(row, dict)]


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return dict(value) if isinstance(value, dict) else {}


def _nested(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("Name", "name", "Label", "label", "Abbreviation", "abbreviation", "Id", "id"):
        if key in value and value[key] is not None:
            return value[key]
    return None


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return _nested(source[key])
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


def _finished(source: dict[str, Any]) -> bool | None:
    for key in ("IsFinished", "isFinished", "Finished", "finished"):
        if key not in source:
            continue
        value = source[key]
        if isinstance(value, bool):
            return value
        token = _text(value).casefold()
        if token in {"true", "1", "yes"}:
            return True
        if token in {"false", "0", "no"}:
            return False
    for key in ("FinishedDate", "finishedDate", "FinishedDateTime"):
        if key in source:
            return bool(_text(source.get(key)))
    status = _text(_first(source, "Status", "PackageState", "State")).casefold()
    if status in {"finished", "inactive", "discontinued"}:
        return True
    if status in {"active", "available", "onhold", "on hold", "quarantine"}:
        return False
    return None


def package_snapshot(readback: Any) -> dict[str, Any]:
    records = _records(readback)
    if len(records) != 1:
        return {"ok": False, "reason": "Fresh package readback must return exactly one provider object."}
    record = records[0]
    source = _source(record)
    provider_id = _text(record.get("provider_id") or _first(source, "Id", "id"))
    label = _text(record.get("label") or _first(source, "Label", "PackageLabel", "Tag"))
    item = _text(_first(source, "ItemName", "Item", "ProductName"))
    quantity = _number(record.get("quantity") if record.get("quantity") is not None else _first(source, "Quantity", "CurrentQuantity"))
    unit = _text(record.get("unit_of_measure") or _first(source, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure"))
    location = _text(_first(source, "LocationName", "Location", "RoomName"))
    return {
        "ok": bool(provider_id),
        "provider_id": provider_id,
        "label": label,
        "item": item,
        "quantity": quantity,
        "unit_of_measure": unit,
        "location": location,
        "finished": _finished(source),
        "last_modified": _text(record.get("last_modified")),
        "source": source,
    }


def verify_package_state(
    *,
    readback: Any,
    provider_id: str,
    expected_label: str = "",
    expected_item: str = "",
    expected_quantity: float | None = None,
    expected_unit: str = "",
    expected_finished: bool | None = None,
    expected_location: str = "",
) -> dict[str, Any]:
    snapshot = package_snapshot(readback)
    differences: list[dict[str, Any]] = []
    if not snapshot.get("ok"):
        return {"matched": False, "differences": [{"field": "readback", "expected": "one package", "actual": snapshot.get("reason", "unavailable")}], "snapshot": snapshot}

    def compare(field: str, expected: Any, actual: Any) -> None:
        if not _same_text(expected, actual):
            differences.append({"field": field, "expected": expected, "actual": actual})

    compare("provider_id", provider_id, snapshot.get("provider_id"))
    if expected_label:
        compare("label", expected_label, snapshot.get("label"))
    if expected_item:
        compare("item", expected_item, snapshot.get("item"))
    if expected_quantity is not None:
        actual = snapshot.get("quantity")
        if actual is None or not isclose(float(actual), float(expected_quantity), rel_tol=1e-9, abs_tol=1e-6):
            differences.append({"field": "quantity", "expected": float(expected_quantity), "actual": actual})
    if expected_unit:
        compare("unit_of_measure", expected_unit, snapshot.get("unit_of_measure"))
    if expected_finished is not None and snapshot.get("finished") is not expected_finished:
        differences.append({"field": "finished", "expected": expected_finished, "actual": snapshot.get("finished")})
    if expected_location:
        compare("location", expected_location, snapshot.get("location"))
    return {"matched": not differences, "differences": differences, "snapshot": snapshot}
