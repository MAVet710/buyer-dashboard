"""Canonical parsing of capability and identity fields from Metrc facility records."""

from __future__ import annotations

from typing import Any


def _source(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    nested = record.get("source")
    return dict(nested) if isinstance(nested, dict) else dict(record)


def provider_facility_license(record: Any) -> str:
    """Return the exact provider facility license across known Metrc v2 shapes."""

    row = _source(record)
    for key in ("LicenseNumber", "licenseNumber", "Number", "number"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    for key in ("License", "license"):
        nested = row.get(key)
        if not isinstance(nested, dict):
            continue
        for nested_key in ("Number", "number", "LicenseNumber", "licenseNumber"):
            value = nested.get(nested_key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def provider_boolean_capabilities(record: Any) -> dict[str, bool]:
    """Return explicit provider boolean capability evidence without inference.

    Metrc facility responses have appeared with capability flags both on the
    facility object itself and inside ``FacilityType``. Read both shapes so all
    diagnostics make the same applicability decision while preserving Metrc's
    exact capability names and values.
    """

    row = _source(record)
    sources = [row]
    for key in ("FacilityType", "facilityType"):
        nested = row.get(key)
        if isinstance(nested, dict):
            sources.append(nested)

    capabilities: dict[str, bool] = {}
    for source in sources:
        for key, value in source.items():
            name = str(key)
            if isinstance(value, bool) and (name.startswith("Can") or name.startswith("Is")):
                capabilities[name] = value
    return dict(sorted(capabilities.items()))


def provider_capability(record: Any, name: str) -> bool | None:
    value = provider_boolean_capabilities(record).get(str(name or ""))
    return value if isinstance(value, bool) else None
