"""Public, fail-closed entrypoint for scaled DEV Sandbox inventory replacement."""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization
from modules.coman.vertical_demo_inventory import DEV_FACILITY_CODE, DEV_ORGANIZATION_SLUG, VERTICAL_SEED_ACTOR
from modules.coman.vertical_demo_inventory_scale import (
    EXPECTED_ACTIVE_PLANTS,
    EXPECTED_EXTRACT_SKUS,
    EXPECTED_FINISHED_SKUS,
    EXPECTED_FLOWER_SKUS,
    EXPECTED_MOCK_FINISHED_COAS,
    EXPECTED_TOTAL_PLANTS,
    VerticalDevInventoryResult,
    replace_scaled_vertical_dev_inventory as _replace_scaled_vertical_dev_inventory,
    scaled_vertical_inventory_present,
)


def assert_dev_sandbox_scope(engine: Engine, organization_id: str, facility_id: str) -> None:
    """Reject any destructive call unless both durable DEV identifiers match exactly."""
    with Session(engine) as session:
        organization = session.get(Organization, organization_id)
        facility = session.get(Facility, facility_id)
        if organization is None or organization.slug != DEV_ORGANIZATION_SLUG:
            raise RuntimeError("DEV inventory replacement is restricted to the dev-sandbox organization.")
        if (
            facility is None
            or facility.organization_id != organization.id
            or facility.code != DEV_FACILITY_CODE
        ):
            raise RuntimeError("DEV inventory replacement is restricted to the dev-sandbox SANDBOX facility.")


def replace_scaled_vertical_dev_inventory(
    engine: Engine,
    organization_id: str,
    facility_id: str,
    *,
    generation: str,
    actor: str = VERTICAL_SEED_ACTOR,
) -> VerticalDevInventoryResult:
    """Guard tenant scope before *any* plant, order, inventory, or catalog mutation."""
    assert_dev_sandbox_scope(engine, organization_id, facility_id)
    return _replace_scaled_vertical_dev_inventory(
        engine,
        organization_id,
        facility_id,
        generation=generation,
        actor=actor,
    )


__all__ = [
    "EXPECTED_ACTIVE_PLANTS",
    "EXPECTED_EXTRACT_SKUS",
    "EXPECTED_FINISHED_SKUS",
    "EXPECTED_FLOWER_SKUS",
    "EXPECTED_MOCK_FINISHED_COAS",
    "EXPECTED_TOTAL_PLANTS",
    "VerticalDevInventoryResult",
    "assert_dev_sandbox_scope",
    "replace_scaled_vertical_dev_inventory",
    "scaled_vertical_inventory_present",
]
