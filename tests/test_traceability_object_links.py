from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, Organization
from modules.traceability.models import TraceabilityTransaction
from modules.traceability.object_links import TraceabilityObjectLink, TraceabilityObjectLinkRepository


def _repository() -> TraceabilityObjectLinkRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TraceabilityTransaction.__table__.create(engine)
    TraceabilityObjectLink.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-1", name="Grower", slug="grower"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Grow", code="GROW"))
        session.add(Organization(id="org-2", name="Other", slug="other"))
        session.add(Facility(id="fac-2", organization_id="org-2", name="Other", code="OTHER"))
    return TraceabilityObjectLinkRepository(engine)


def _link(repo: TraceabilityObjectLinkRepository, *, entity_type: str = "plant_group", entity_id: str = "group-1", provider_id: str = "101"):
    return repo.upsert_verified(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        jurisdiction="MA",
        environment="sandbox",
        license_number="LIC-1",
        entity_type=entity_type,
        entity_id=entity_id,
        provider_resource="plant_batches",
        provider_id=provider_id,
        provider_label="GMO-CLONES-001",
    )


def test_verified_link_is_idempotent_and_exact():
    repo = _repository()
    first = _link(repo)
    second = _link(repo)

    assert first.id == second.id
    assert second.status == "verified"
    assert second.provider_id == "101"
    assert second.provider_label == "GMO-CLONES-001"
    fetched = repo.get_local(
        organization_id="org-1",
        facility_id="fac-1",
        provider="metrc",
        environment="sandbox",
        entity_type="plant_group",
        entity_id="group-1",
    )
    assert fetched is not None
    assert fetched.id == first.id


def test_local_object_cannot_be_silently_rebound_to_different_provider_id():
    repo = _repository()
    _link(repo)
    with pytest.raises(ValueError, match="already linked to a different provider identity"):
        _link(repo, provider_id="202")


def test_provider_object_cannot_be_linked_to_two_local_objects():
    repo = _repository()
    _link(repo)
    with pytest.raises(ValueError, match="already linked to a different DoobieLogic object"):
        _link(repo, entity_id="group-2", provider_id="101")


def test_link_can_be_marked_for_reconciliation_without_losing_identity():
    repo = _repository()
    row = _link(repo)
    updated = repo.mark_reconciliation_required(
        organization_id="org-1",
        facility_id="fac-1",
        link_id=row.id,
        reason="Provider name changed outside DoobieLogic.",
    )
    assert updated.status == "reconciliation_required"
    assert updated.provider_id == "101"
    assert "outside DoobieLogic" in updated.mismatch_reason


def test_object_link_queries_are_tenant_safe():
    repo = _repository()
    _link(repo)
    assert repo.get_local(
        organization_id="org-2",
        facility_id="fac-2",
        provider="metrc",
        environment="sandbox",
        entity_type="plant_group",
        entity_id="group-1",
    ) is None
    assert repo.list_facility(organization_id="org-2", facility_id="fac-2") == []
