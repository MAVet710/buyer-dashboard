"""Read-only Metrc resources for manufacturing and cultivation operations.

These helpers only call normalized GET resources that have already passed the
jurisdiction capability and environment gates in ``modules.regulatory``.
Nothing in this module mutates Metrc or DoobieLogic.
"""

from __future__ import annotations

from typing import Any

from services.metrc_receiving import _paged_resource_get


def _fetch_all(
    *,
    resource: str,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource=resource,
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_active_processing_jobs(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _fetch_all(
        resource="processing_active",
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        license_number=license_number,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_active_plant_batches(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _fetch_all(
        resource="plant_batches_active",
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        license_number=license_number,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_vegetative_plants(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _fetch_all(
        resource="plants_vegetative",
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        license_number=license_number,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_flowering_plants(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _fetch_all(
        resource="plants_flowering",
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        license_number=license_number,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_active_harvests(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    license_number: str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _fetch_all(
        resource="harvests_active",
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        license_number=license_number,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
