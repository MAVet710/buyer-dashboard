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

    result = _paged_resource_get(
        state=state,
        user_api_key=user_api_key,
        integrator_api_key=integrator_api_key,
        resource="packages_active",
        environment=environment,
        license_number=license_number,
        timeout_seconds=timeout_seconds,
    )
    if result.get("ok"):
        # Generic normalization may surface PackageState before LabTestingState.
        # Reconciliation specifically compares lab disposition, so preserve the
        # provider record losslessly while projecting the direct lab field into
        # the normalized status used by the deterministic comparator.
        for record in result.get("records") or []:
            if not isinstance(record, dict):
                continue
            source = record.get("source") if isinstance(record.get("source"), dict) else {}
            lab_state = source.get("LabTestingState") or source.get("LabTestResultStatus")
            if lab_state is not None and str(lab_state).strip():
                record["status"] = str(lab_state).strip()
    return result
