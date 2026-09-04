from __future__ import annotations

from typing import Any

from services.metrc_client import MetrcTransport


class MetrcPackageReferenceError(ValueError):
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


def fetch_package_adjustment_reasons(
    *,
    state: str,
    environment: str,
    integrator_api_key: str,
    user_api_key: str,
    transport: MetrcTransport | None = None,
) -> dict[str, Any]:
    client = transport or MetrcTransport(
        state=state,
        environment=environment,
        integrator_api_key=integrator_api_key,
        user_api_key=user_api_key,
    )
    result = client.get("packages/v2/adjust/reasons", {"pageSize": 100, "pageNumber": 1})
    if not isinstance(result, dict) or not result.get("ok"):
        raise MetrcPackageReferenceError(
            str((result or {}).get("message") if isinstance(result, dict) else "")
            or "Metrc package adjustment reasons could not be loaded."
        )
    names: list[str] = []
    seen: set[str] = set()
    for row in _rows(result.get("payload")):
        name = str(row.get("Name") or row.get("name") or "").strip()
        key = name.casefold()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    if not names:
        raise MetrcPackageReferenceError(
            "Metrc returned no usable package adjustment reasons; adjustment submission remains blocked."
        )
    return {
        "ok": True,
        "items": sorted(names, key=str.casefold),
        "http_status": int(result.get("http_status") or 200),
        "correlation_id": str(result.get("correlation_id") or ""),
        "bounded_page_size": 100,
    }
