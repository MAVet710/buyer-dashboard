from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.metrc_runtime_composition import FULL_SYNC_PAGE_SAFETY_CEILING, compose_metrc_runtime
from backend.app.services.metrc_natural_sync import _expected_resources
from backend.app.services.metrc_sync_policy import MetrcPolicySyncControlService
from modules.coman.models import Base, Facility, Organization, utc_now
from modules.integrations.models import IntegrationSyncAttempt, IntegrationSyncState


def _engine():
    compose_metrc_runtime()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-policy", name="Policy", slug="policy"))
        session.add(Facility(
            id="fac-policy",
            organization_id="org-policy",
            name="Policy Facility",
            code="MC-POLICY",
            license_number="MC281234",
            cultivation_enabled=True,
            production_enabled=True,
        ))
    return engine


def _seed_full_baseline(engine, *, age_hours: int = 0):
    completed = utc_now() - timedelta(hours=age_hours)
    with Session(engine) as session, session.begin():
        for resource in _expected_resources():
            session.add(IntegrationSyncState(
                organization_id="org-policy",
                facility_id="fac-policy",
                provider="metrc",
                resource=resource,
                environment="sandbox",
                cursor="initial-full",
                status="succeeded",
                last_started_at=completed,
                last_completed_at=completed,
                last_success_at=completed,
                records_seen=1,
                records_written=1,
                updated_by="tester",
            ))
            session.add(IntegrationSyncAttempt(
                organization_id="org-policy",
                facility_id="fac-policy",
                provider="metrc",
                resource=resource,
                run_id=str(uuid4()),
                status="succeeded",
                cursor_before="",
                cursor_after="initial-full",
                record_count=1,
                accepted_count=1,
                duplicate_count=0,
                error_count=0,
                error_message="",
                actor="tester",
                started_at=completed,
                completed_at=completed,
            ))


def test_full_refresh_is_not_due_inside_24_hour_window():
    engine = _engine()
    _seed_full_baseline(engine, age_hours=1)
    evidence = MetrcPolicySyncControlService(engine)._full_refresh_evidence(
        organization_id="org-policy",
        facility_id="fac-policy",
        environment="sandbox",
    )
    assert evidence["due"] is False
    assert evidence["interval_hours"] == 24
    assert evidence["missing_full_baseline_resources"] == []
    assert evidence["full_only_resource_count"] > 0


def test_full_refresh_becomes_due_after_24_hours():
    engine = _engine()
    _seed_full_baseline(engine, age_hours=25)
    evidence = MetrcPolicySyncControlService(engine)._full_refresh_evidence(
        organization_id="org-policy",
        facility_id="fac-policy",
        environment="sandbox",
    )
    assert evidence["due"] is True
    assert evidence["next_full_refresh_at"] is not None


def test_permission_skipped_resource_does_not_block_full_refresh_evidence():
    engine = _engine()
    _seed_full_baseline(engine, age_hours=1)
    exempt = _expected_resources()[0]
    with Session(engine) as session, session.begin():
        state = session.scalar(select(IntegrationSyncState).where(
            IntegrationSyncState.organization_id == "org-policy",
            IntegrationSyncState.facility_id == "fac-policy",
            IntegrationSyncState.resource == exempt,
        ))
        state.cursor = "permission-skipped"
        attempts = list(session.scalars(select(IntegrationSyncAttempt).where(
            IntegrationSyncAttempt.organization_id == "org-policy",
            IntegrationSyncAttempt.facility_id == "fac-policy",
            IntegrationSyncAttempt.resource == exempt,
        )))
        for row in attempts:
            session.delete(row)

    evidence = MetrcPolicySyncControlService(engine)._full_refresh_evidence(
        organization_id="org-policy",
        facility_id="fac-policy",
        environment="sandbox",
    )
    assert exempt not in evidence["missing_full_baseline_resources"]
    assert evidence["due"] is False


def test_runtime_raises_real_facility_page_safety_ceiling_to_one_million_records():
    from services import metrc_facility_bootstrap, metrc_incremental_sync, metrc_resilient_bootstrap

    compose_metrc_runtime()
    assert FULL_SYNC_PAGE_SAFETY_CEILING == 10_000
    assert metrc_facility_bootstrap.MAX_INITIAL_PAGES == 10_000
    assert metrc_resilient_bootstrap.MAX_INITIAL_PAGES == 10_000
    assert metrc_incremental_sync.MAX_INITIAL_PAGES == 10_000
