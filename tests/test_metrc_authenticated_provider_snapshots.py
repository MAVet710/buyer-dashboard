from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.integrations.models import IntegrationProviderSnapshot
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Authenticated Snapshot", slug="authenticated-snapshot", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Snapshot Facility",
            code="MP281234",
            license_number="MP281234",
            production_enabled=True,
            cultivation_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, organization.id, facility.id


def test_authenticated_bootstrap_replaces_current_membership_without_erasing_audit_history(monkeypatch):
    engine, organization_id, facility_id = _engine()
    current_items = [
        {"source": {"Id": 101, "Name": "GMO Flower"}},
        {"source": {"Id": 102, "Name": "Live Resin"}},
    ]

    def fake_normalized(**kwargs):
        resource = kwargs["resource"]
        records = current_items if resource == "items_active" else [{"source": {"Id": f"{resource}-1", "Name": resource}}]
        return {"ok": True, "http_status": 200, "records": [dict(row) for row in records]}

    def fake_get(self, path, params=None, **_kwargs):
        return {"ok": True, "http_status": 200, "payload": [{"Id": f"{path}-1", "Name": path}]}

    monkeypatch.setattr("services.metrc_facility_bootstrap.fetch_metrc_resource", fake_normalized)
    monkeypatch.setattr("services.metrc_facility_bootstrap.MetrcTransport.get", fake_get)

    service = SnapshottingMetrcFacilityBootstrapService(engine)
    first = service.sync(
        organization_id=organization_id,
        facility_id=facility_id,
        license_number="MP281234",
        state="MA",
        environment="sandbox",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        actor="admin",
        facility_record={"Id": 81722, "Name": "Snapshot Facility"},
    )

    assert first["totals"]["failed"] == 0
    assert all(
        row.get("current_snapshot", {}).get("status") == "current"
        for row in first["resources"]
        if row["status"] == "succeeded"
    )

    with Session(engine) as session:
        items = list(
            session.scalars(
                select(IntegrationProviderSnapshot).where(
                    IntegrationProviderSnapshot.organization_id == organization_id,
                    IntegrationProviderSnapshot.facility_id == facility_id,
                    IntegrationProviderSnapshot.provider == "metrc",
                    IntegrationProviderSnapshot.environment == "sandbox",
                    IntegrationProviderSnapshot.resource == "items",
                )
            )
        )
    assert len(items) == 2
    assert {row.external_id for row in items if row.present} == {"101", "102"}

    current_items[:] = [{"source": {"Id": 102, "Name": "Live Resin"}}]
    second = service.sync(
        organization_id=organization_id,
        facility_id=facility_id,
        license_number="MP281234",
        state="MA",
        environment="sandbox",
        integrator_api_key="vendor-key",
        user_api_key="user-key",
        actor="admin",
    )
    assert second["totals"]["failed"] == 0

    with Session(engine) as session:
        items = list(
            session.scalars(
                select(IntegrationProviderSnapshot).where(
                    IntegrationProviderSnapshot.organization_id == organization_id,
                    IntegrationProviderSnapshot.facility_id == facility_id,
                    IntegrationProviderSnapshot.resource == "items",
                )
            )
        )
    assert len(items) == 2
    assert {row.external_id for row in items if row.present} == {"102"}
    assert {row.external_id for row in items if not row.present} == {"101"}


def test_incomplete_or_permission_skipped_read_does_not_clear_current_snapshot():
    engine, organization_id, facility_id = _engine()
    service = SnapshottingMetrcFacilityBootstrapService(engine)

    complete = service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource="locations",
        environment="sandbox",
        actor="admin",
        result={
            "ok": True,
            "http_status": 200,
            "records": [{"source": {"Id": 11, "Name": "Flower 1"}}],
            "page_count": 1,
            "truncated": False,
        },
        transport="test",
    )
    assert complete["current_snapshot"]["status"] == "current"

    incomplete = service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource="locations",
        environment="sandbox",
        actor="admin",
        result={
            "ok": True,
            "http_status": 200,
            "records": [{"source": {"Id": 12, "Name": "Flower 2"}}],
            "page_count": 100,
            "truncated": True,
        },
        transport="test",
    )
    assert incomplete["current_snapshot"]["status"] == "unchanged_incomplete_read"

    skipped = service._persist_fetch_result(
        organization_id=organization_id,
        facility_id=facility_id,
        resource="locations",
        environment="sandbox",
        actor="admin",
        result={"ok": False, "http_status": 403, "status": "forbidden", "message": "permission denied"},
        transport="test",
    )
    assert skipped["current_snapshot"]["status"] == "unchanged_permission_skipped"

    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(IntegrationProviderSnapshot).where(
                    IntegrationProviderSnapshot.organization_id == organization_id,
                    IntegrationProviderSnapshot.facility_id == facility_id,
                    IntegrationProviderSnapshot.resource == "locations",
                )
            )
        )
    assert len(rows) == 1
    assert rows[0].external_id == "11"
    assert rows[0].present is True


def test_router_composition_uses_snapshotting_authenticated_bootstrap():
    from backend.app.routers import sandbox_integrations

    assert sandbox_integrations.MetrcFacilityBootstrapService is SnapshottingMetrcFacilityBootstrapService
