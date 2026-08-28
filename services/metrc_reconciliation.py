from __future__ import annotations

from typing import Any

from services.metrc_receiving import _paged_resource_get


def fetch_all_active_metrc_packages(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """Read every active Metrc package for one exact facility license.

    The underlying paginated read is capability-gated before each request and
    remains read-only. Normalized records are returned for deterministic
    reconciliation while the provider payload stays preserved under ``source``.
    """

    return _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="packages_active",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )
