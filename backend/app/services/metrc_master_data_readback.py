from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping


# Metrc read models do not always use the exact write-model key names.
# Keep aliases explicit and fail closed when no reviewed field can be found.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ItemCategory": ("ItemCategory", "ItemCategoryName", "ProductCategoryName", "CategoryName"),
    "UnitOfMeasure": ("UnitOfMeasure", "UnitOfMeasureName", "UnitOfMeasureAbbreviation"),
    "ItemBrand": ("ItemBrand", "BrandName", "ItemBrandName"),
    "Strain": ("Strain", "StrainName"),
    "LocationTypeName": ("LocationTypeName", "LocationType"),
    "UnitWeightUnitOfMeasure": (
        "UnitWeightUnitOfMeasure",
        "UnitWeightUnitOfMeasureName",
        "UnitWeightUnitOfMeasureAbbreviation",
    ),
}


def _key_lookup(source: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).casefold(): str(key) for key in source}


def _canonical_scalar(value: Any) -> tuple[str, Any]:
    if value is None:
        return ("empty", None)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            return ("number", Decimal(str(value)).normalize())
        except InvalidOperation:
            pass
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return ("empty", None)
        lowered = stripped.casefold()
        if lowered in {"true", "false"}:
            return ("bool", lowered == "true")
        try:
            return ("number", Decimal(stripped).normalize())
        except InvalidOperation:
            return ("text", stripped.casefold())
    return ("json", json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def _equal(requested: Any, actual: Any) -> bool:
    return _canonical_scalar(requested) == _canonical_scalar(actual)


def _source_record(readback: Mapping[str, Any], provider_id: str) -> Mapping[str, Any] | None:
    records = readback.get("records")
    if not isinstance(records, list):
        return None
    target = str(provider_id or "").strip()
    fallback: Mapping[str, Any] | None = None
    for record in records:
        if not isinstance(record, Mapping):
            continue
        source = record.get("source")
        candidate = source if isinstance(source, Mapping) else record
        if fallback is None:
            fallback = candidate
        record_id = str(
            record.get("provider_id")
            or candidate.get("Id")
            or candidate.get("ID")
            or candidate.get("id")
            or ""
        ).strip()
        if target and record_id == target:
            return candidate
    return fallback if len(records) == 1 else None


def compare_master_data_readback(
    *,
    provider_request_body: Any,
    readback: Mapping[str, Any] | None,
    provider_id: str,
) -> dict[str, Any]:
    """Compare every reviewed write field with the fresh Metrc readback.

    Provider ID equality is necessary but not sufficient. Every bounded field
    reviewed by the operator must be observable on readback and equal after
    normalization; otherwise the action stays in reconciliation_required.
    """

    request_row = provider_request_body[0] if isinstance(provider_request_body, list) and provider_request_body else None
    if not isinstance(request_row, Mapping):
        return {"matched": False, "differences": [{"field": "body", "reason": "reviewed provider body is missing"}]}
    if not isinstance(readback, Mapping) or not readback.get("ok"):
        return {"matched": False, "differences": [{"field": "readback", "reason": "fresh provider readback is unavailable"}]}

    source = _source_record(readback, provider_id)
    if not isinstance(source, Mapping):
        return {"matched": False, "differences": [{"field": "readback", "reason": "provider object was not found in fresh readback"}]}

    lookup = _key_lookup(source)
    differences: list[dict[str, Any]] = []
    compared: list[str] = []
    for field, requested in request_row.items():
        if str(field).casefold() == "id":
            continue
        aliases = _FIELD_ALIASES.get(str(field), (str(field),))
        actual_key = next((lookup.get(alias.casefold()) for alias in aliases if lookup.get(alias.casefold())), None)
        if actual_key is None:
            differences.append({"field": str(field), "reason": "field missing from fresh provider readback", "requested": requested})
            continue
        actual = source.get(actual_key)
        compared.append(str(field))
        if not _equal(requested, actual):
            differences.append({"field": str(field), "reason": "value mismatch", "requested": requested, "actual": actual})

    return {
        "matched": not differences,
        "compared_fields": compared,
        "differences": differences,
    }
