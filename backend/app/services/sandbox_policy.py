"""Canonical DEV Sandbox execution policy shared by operator-facing APIs.

The policy makes rehearsal capabilities explicit without weakening production
compliance or provider-write guardrails. Only DEV/Admin users inside the durable
``dev-sandbox`` / ``SANDBOX`` tenant receive relaxed local test capabilities.
"""
from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization
from services.sandbox_system_contract import is_dev_sandbox_scope

SANDBOX_TEST_ARTIFACT_MARK = "SANDBOX TEST · NOT FOR SALE"


def sandbox_execution_policy(
    engine: Engine,
    *,
    organization_id: str,
    facility_id: str,
    role: str,
) -> dict[str, object]:
    with Session(engine) as session:
        organization = session.get(Organization, organization_id)
        facility = session.get(Facility, facility_id)
        canonical_scope = bool(
            organization is not None
            and facility is not None
            and facility.organization_id == organization_id
            and is_dev_sandbox_scope(organization, facility)
        )

    developer = str(role or "").strip().casefold() in {"dev", "admin"}
    enabled = canonical_scope and developer
    return {
        "canonical_dev_sandbox": canonical_scope,
        "developer_authorized": developer,
        "operator_rehearsal_enabled": enabled,
        "label_layout_testing_enabled": enabled,
        "local_mutations_enabled": enabled,
        # Exact external provider writes remain independently fail-closed until
        # request + acknowledgement + readback evidence is proven in sandbox.
        "external_provider_writes_enabled": False,
        "provider_transport": "deterministic_fixture",
        "test_artifact_mark": SANDBOX_TEST_ARTIFACT_MARK if enabled else "",
        "production_guardrails_intact": True,
    }


__all__ = ["SANDBOX_TEST_ARTIFACT_MARK", "sandbox_execution_policy"]
