"""Read-only Metrc helpers for wholesale/distribution regulatory visibility.

All network calls in this module are GET-only normalized resources. Transfer
acceptance, manifest creation, delivery edits, and package mutations remain out
of scope until DoobieLogic has an explicit approved action framework.
"""

from __future__ import annotations

from typing import Any

from services.metrc_receiving import _paged_resource_get


def fetch_all_outgoing_transfers(
    *,
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
        resource="outgoing_transfers",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_outgoing_transfer_templates(
    *,
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
        resource="transfer_templates_outgoing",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_transporter_drivers(
    *,
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
        resource="transporter_drivers",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_transporter_vehicles(
    *,
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
        resource="transporter_vehicles",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )


def fetch_all_wholesale_delivery_packages(
    *,
    state: str,
    user_api_key: str,
    integrator_api_key: str,
    delivery_id: int | str,
    environment: str = "production",
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    return _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="wholesale_delivery_packages",
        environment=environment,
        path_parameters={"delivery_id": delivery_id},
        timeout_seconds=timeout_seconds,
    )
