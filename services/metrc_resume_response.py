"""Strict response parsing for the MA evaluation; no provider I/O or credentials."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit


class ResumeResponseError(ValueError):
    """A provider response cannot safely support an evaluation decision."""


def validate_sandbox_url(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != "https" or url.netloc.lower() != "sandbox-api-ma.metrc.com"
            or url.path not in ("", "/") or url.query or url.fragment):
        raise ResumeResponseError("An exact HTTPS Massachusetts sandbox origin is required.")
    return "https://sandbox-api-ma.metrc.com"


def collection_values(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        for key in ("Data", "data"):
            if isinstance(payload.get(key), list):
                return list(payload[key])
    raise ResumeResponseError("Expected a provider list or Data-list envelope.")


def object_rows(payload: Any) -> list[dict[str, Any]]:
    values = collection_values(payload)
    if any(not isinstance(value, dict) for value in values):
        raise ResumeResponseError("Expected object records; refusing to discard provider values.")
    return [dict(value) for value in values]


def reference_names(payload: Any) -> list[str]:
    """Reference endpoints can return strings rather than object records."""
    names: list[str] = []
    for value in collection_values(payload):
        name = value if isinstance(value, str) else None
        if isinstance(value, dict):
            name = next((value[key] for key in ("Name", "name", "TagType", "tagType")
                         if isinstance(value.get(key), str)), None)
        if not isinstance(name, str) or not name.strip():
            raise ResumeResponseError("Unrecognized reference value; not an empty reference list.")
        if name.strip() not in names:
            names.append(name.strip())
    return names


def total_pages(payload: Any, *, maximum: int = 1000) -> int:
    """Honor top-level v2 pagination; also accept the existing Meta envelope."""
    if isinstance(payload, list):
        return 1
    if not isinstance(payload, dict):
        raise ResumeResponseError("Malformed pagination response.")
    values: list[int] = []
    containers = [payload]
    if isinstance(payload.get("Meta"), dict):
        containers.append(payload["Meta"])
    for container in containers:
        for key in ("TotalPages", "totalPages"):
            if key not in container:
                continue
            raw = container[key]
            if isinstance(raw, bool) or not str(raw).isdigit():
                raise ResumeResponseError("Invalid provider TotalPages.")
            count = int(raw)
            if count > maximum:
                raise ResumeResponseError("Provider pagination exceeds the safety ceiling.")
            values.append(count)
    if not values:
        raise ResumeResponseError("Paginated envelope has no TotalPages; completeness is unknown.")
    if len(set(values)) != 1:
        raise ResumeResponseError("Conflicting provider pagination metadata.")
    if values[0] == 0 and collection_values(payload):
        raise ResumeResponseError("Zero pages cannot contain provider records.")
    return max(1, values[0])


def numeric(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ResumeResponseError("Missing or non-numeric provider quantity.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ResumeResponseError("Invalid provider quantity.") from exc
    if not result.is_finite():
        raise ResumeResponseError("Non-finite provider quantity.")
    return result


def package_record(payload: Any, label: str) -> dict[str, Any]:
    if isinstance(payload, dict) and "Id" in payload:
        values = [payload]
    else:
        values = object_rows(payload)
    matches = [row for row in values if row.get("Label") == label]
    if len(matches) != 1 or not matches[0].get("Id"):
        raise ResumeResponseError("Fresh readback did not identify exactly the requested package.")
    return matches[0]


def verify_package(row: dict[str, Any], *, label: str, item_name: str,
                   quantity: Any, unit: str, provider_id: Any = None) -> None:
    if row.get("Label") != label or not row.get("Id"):
        raise ResumeResponseError("Package identity did not match the requested mutation.")
    if provider_id is not None and str(row["Id"]) != str(provider_id):
        raise ResumeResponseError("Package provider ID changed.")
    item = row.get("Item")
    if not isinstance(item, dict) or item.get("Name") != item_name:
        raise ResumeResponseError("Readback item differs from the submitted item.")
    if numeric(row.get("Quantity")) != numeric(quantity):
        raise ResumeResponseError("Readback quantity differs from the expected quantity.")
    if row.get("UnitOfMeasureName") != unit:
        raise ResumeResponseError("Readback unit differs from the expected unit.")
    if row.get("IsFinished") is not False or row.get("IsOnHold") is not False:
        raise ResumeResponseError("Package is finished, held, or has unknown availability.")
