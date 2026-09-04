from __future__ import annotations

from typing import Any

from services.metrc_client import MetrcTransport


class MetrcHarvestReferenceError(ValueError):
    pass


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("Data", "data", "Results", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, dict)]
    return []


def fetch_harvest_waste_types(
    *,
    state: str,
    environment: str,
    integrator_api_key: str,
    user_api_key: str,
    transport: MetrcTransport | None = None,
) -> dict[str, Any]:
    """Fetch the bounded provider reference list used by harvest waste writes."""

    client = transport or MetrcTransport(
        state=state,
        environment=environment,
        integrator_api_key=integrator_api_key,
        user_api_key=user_api_key,
    )
    result = client.get(
        "harvests/v2/waste/types",
        {"pageSize": 100, "pageNumber": 1},
    )
    if not isinstance(result, dict) or not result.get("ok"):
        raise MetrcHarvestReferenceError(
            str((result or {}).get("message") if isinstance(result, dict) else "")
            or "Metrc harvest waste types could not be loaded."
        )

    names: list[str] = []
    seen: set[str] = set()
    for row in _rows(result.get("payload")):
        name = str(row.get("Name") or row.get("name") or "").strip()
        normalized = name.casefold()
        if name and normalized not in seen:
            names.append(name)
            seen.add(normalized)
    if not names:
        raise MetrcHarvestReferenceError(
            "Metrc returned no usable harvest waste types; waste submission remains blocked."
        )
    return {
        "ok": True,
        "items": sorted(names, key=str.casefold),
        "http_status": int(result.get("http_status") or 200),
        "correlation_id": str(result.get("correlation_id") or ""),
        "bounded_page_size": 100,
    }
