from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.cultivation_regulatory_guard import CultivationRegulatoryGuard
from modules.coman.models import Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from modules.traceability.models import TraceabilityTransaction
from modules.traceability.object_links import TraceabilityObjectLink, TraceabilityObjectLinkRepository


def _guard():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityObjectLink.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1", name="Grower", slug="grower"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Grow", code="GROW"))
    return CultivationRegulatoryGuard(engine), TraceabilityObjectLinkRepository(engine), engine


def _link(repo: TraceabilityObjectLinkRepository, entity_id: str, entity_type: str = "cultivation_plant"):
    return repo.upsert_verified(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        jurisdiction="MA",
        environment="sandbox",
        license_number="LIC-1",
        entity_type=entity_type,
        entity_id=entity_id,
        provider_resource="plants" if entity_type == "cultivation_plant" else "plant_batches",
        provider_id=f"provider-{entity_id}",
        provider_label=f"TAG-{entity_id}",
    )


def test_untracked_local_object_remains_eligible_for_local_workflow():
    guard, _repo, _engine = _guard()
    guard.require_local_only_allowed(
        organization_id="org-1",
        facility_id="fac-1",
        entity_type="cultivation_plant",
        entity_ids=["plant-local"],
        action_label="Move plant",
    )


def test_verified_tracked_plant_blocks_local_only_mutation():
    guard, repo, _engine = _guard()
    _link(repo, "plant-1")
    with pytest.raises(ValueError, match="state-system identity"):
        guard.require_local_only_allowed(
            organization_id="org-1",
            facility_id="fac-1",
            entity_type="cultivation_plant",
            entity_ids=["plant-1"],
            action_label="Move plant",
        )


def test_bulk_guard_detects_any_tracked_member_setwise():
    guard, repo, _engine = _guard()
    _link(repo, "plant-2")
    tracked = guard.verified_metrc_ids(
        organization_id="org-1",
        facility_id="fac-1",
        entity_type="cultivation_plant",
        entity_ids=["plant-1", "plant-2", "plant-3"],
    )
    assert tracked == {"plant-2"}
    with pytest.raises(ValueError, match="1 selected cultivation object"):
        guard.require_local_only_allowed(
            organization_id="org-1",
            facility_id="fac-1",
            entity_type="cultivation_plant",
            entity_ids=["plant-1", "plant-2", "plant-3"],
            action_label="Bulk move",
        )


def test_verified_group_blocks_legacy_local_group_transition():
    guard, repo, _engine = _guard()
    _link(repo, "group-1", entity_type="cultivation_group")
    with pytest.raises(ValueError, match="controlled Metrc workflow"):
        guard.require_local_only_allowed(
            organization_id="org-1",
            facility_id="fac-1",
            entity_type="cultivation_group",
            entity_ids=["group-1"],
            action_label="Group transition",
        )


def test_initial_batch_sync_in_flight_blocks_local_group_change_before_provider_link_exists():
    guard, _repo, engine = _guard()
    TraceabilityBackofficeRepository(engine).create_transaction(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        operation_type="plant_batch_sync",
        entity_type="cultivation_group",
        entity_id="group-pending",
        idempotency_key="pending-sync-1",
        actor="operator-1",
        license_number="LIC-1",
        jurisdiction="MA",
        environment="sandbox",
        request_payload={"bounded": True},
        local_state={"phase": "clone"},
        reason="Operator confirmed batch sync",
    )
    assert guard.unresolved_metrc_ids(
        organization_id="org-1",
        facility_id="fac-1",
        entity_type="cultivation_group",
        entity_ids=["group-pending"],
    ) == {"group-pending"}
    with pytest.raises(ValueError, match="in-flight or reconciliation-required"):
        guard.require_local_only_allowed(
            organization_id="org-1",
            facility_id="fac-1",
            entity_type="cultivation_group",
            entity_ids=["group-pending"],
            action_label="Local group transition",
        )
