"""Narrow, server-side policy for DEV Sandbox test passes.

The pass is intentionally not a generic development-mode switch. It is active
only when all three facts are true at the same time:

* authenticated role is ``dev``
* organization slug is exactly ``dev-sandbox``
* facility code is exactly ``SANDBOX`` and belongs to that organization

Production/customer tenants therefore keep every normal safety and compliance
gate even when the same DEV user can access them.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization

DEV_SANDBOX_ORGANIZATION_SLUG = "dev-sandbox"
DEV_SANDBOX_FACILITY_CODE = "SANDBOX"
DEV_SANDBOX_TEST_PASS_REASON = "DEV Sandbox test pass"


def dev_sandbox_test_pass_active(
    session: Session,
    organization_id: str,
    facility_id: str,
    role: str | None,
) -> bool:
    """Return True only for the canonical DEV Sandbox tenant/facility scope."""
    if str(role or "").strip().casefold() != "dev":
        return False
    organization = session.get(Organization, organization_id)
    facility = session.get(Facility, facility_id)
    if organization is None or facility is None:
        return False
    return bool(
        facility.organization_id == organization.id
        and str(organization.slug or "").strip().casefold() == DEV_SANDBOX_ORGANIZATION_SLUG
        and str(facility.code or "").strip().casefold() == DEV_SANDBOX_FACILITY_CODE.casefold()
    )


def dev_sandbox_test_pass_audit() -> dict[str, object]:
    """Stable audit payload used by guarded sandbox mutations."""
    return {
        "sandbox_test_pass": True,
        "sandbox_scope": f"{DEV_SANDBOX_ORGANIZATION_SLUG}/{DEV_SANDBOX_FACILITY_CODE}",
        "data_classification": "synthetic_test_data",
        "production_effect": "none",
    }
