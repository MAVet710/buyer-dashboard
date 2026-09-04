from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.label_studio_workflow import LabelProductionWorkflowService
from modules.regulatory.metrc_process_models import MetrcTagInventory
from services.metrc_facility_snapshot_bootstrap import SnapshottingMetrcFacilityBootstrapService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Tag Hydration", slug="tag-hydration", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Tag Facility",
            code="MP281234",
            license_number="MP281234",
            production_enabled=True,
            cultivation_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return engine, organization.id, facility.id


def test_authenticated_sync_feeds_plant_and_package_tag_selectors_without_extra_provider_reads(monkeypatch):
    engine, organization_id, facility_id = _engine()
    provider_state = {
        "plant": [{"source": {"Id": "plant-id-1", "Label": "PLANT-TAG-1"}}],
        "package": [{"source": {"Id": "package-id-1", "Label": "PACKAGE-TAG-1"}}],
        "plant_forbidden": False,
    }

    def fake_normalized(**kwargs):
        resource = kwargs["resource"]
        if resource == "plant_tags_available":
            if provider_state["plant_forbidden"]:
                return {"ok": False, "http_status": 403, "status": "forbidden", "message": "No plant tag permission"}
            return {"ok": True, "http_status": 200, "records": list(provider_state["plant"])}
        if resource == "package_tags_available":
            return {"ok": True, "http_status": 200, "records": list(provider_state["package"])}
        return {"ok": True, "http_status": 200, "records": []}

    def fake_get(self, path, params=None, **_kwargs):
        return {"ok": True, "http_status": 200, "payload": []}

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
    )

    assert first["selector_hydration"]["network_request_made"] is False
    assert first["selector_hydration"]["tags"]["plant"]["status"] == "current"
    assert first["selector_hydration"]["tags"]["package"]["status"] == "current"

    with Session(engine) as session:
        tags = list(session.scalars(select(MetrcTagInventory).order_by(MetrcTagInventory.tag_type, MetrcTagInventory.label)))
        assert {(row.tag_type, row.label, row.status) for row in tags} == {
            ("plant", "PLANT-TAG-1", "available"),
            ("package", "PACKAGE-TAG-1", "available"),
        }
        assert LabelProductionWorkflowService(engine)._validate_synced_package_tag(
            session,
            organization_id,
            facility_id,
            "PACKAGE-TAG-1",
            "sandbox",
        ) == "synced_metrc_available"

    # Package tags can keep refreshing independently when a cultivation-specific
    # plant-tag permission is unavailable. The old plant selector state is not
    # erased by the 403, while complete package membership is replaced normally.
    provider_state["plant_forbidden"] = True
    provider_state["package"] = [{"source": {"Id": "package-id-2", "Label": "PACKAGE-TAG-2"}}]
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

    assert second["selector_hydration"]["tags"]["plant"]["status"] == "unchanged"
    assert second["selector_hydration"]["tags"]["plant"]["reason"] == "unchanged_permission_skipped"
    assert second["selector_hydration"]["tags"]["package"]["status"] == "current"

    with Session(engine) as session:
        plant = session.scalar(select(MetrcTagInventory).where(MetrcTagInventory.label == "PLANT-TAG-1"))
        old_package = session.scalar(select(MetrcTagInventory).where(MetrcTagInventory.label == "PACKAGE-TAG-1"))
        new_package = session.scalar(select(MetrcTagInventory).where(MetrcTagInventory.label == "PACKAGE-TAG-2"))
        assert plant is not None and plant.status == "available"
        assert old_package is not None and old_package.status == "unavailable"
        assert new_package is not None and new_package.status == "available"


def test_tag_snapshot_never_resurrects_reserved_used_or_voided_local_lifecycle():
    engine, organization_id, facility_id = _engine()
    with Session(engine) as session, session.begin():
        session.add_all([
            MetrcTagInventory(
                organization_id=organization_id,
                facility_id=facility_id,
                jurisdiction_code="MA",
                license_number="MP281234",
                environment="sandbox",
                tag_type="package",
                label="RESERVED",
                status="reserved",
            ),
            MetrcTagInventory(
                organization_id=organization_id,
                facility_id=facility_id,
                jurisdiction_code="MA",
                license_number="MP281234",
                environment="sandbox",
                tag_type="package",
                label="USED",
                status="used",
            ),
            MetrcTagInventory(
                organization_id=organization_id,
                facility_id=facility_id,
                jurisdiction_code="MA",
                license_number="MP281234",
                environment="sandbox",
                tag_type="package",
                label="VOIDED",
                status="voided",
            ),
        ])

    from services.metrc_available_tag_mirror import MetrcAvailableTagMirror

    result = MetrcAvailableTagMirror(engine).replace(
        organization_id=organization_id,
        facility_id=facility_id,
        jurisdiction_code="MA",
        license_number="MP281234",
        environment="sandbox",
        tag_type="package",
        records=[
            {"Label": "RESERVED"},
            {"Label": "USED"},
            {"Label": "VOIDED"},
        ],
    )
    assert result["protected_local_lifecycle_count"] == 3

    with Session(engine) as session:
        statuses = {
            row.label: row.status
            for row in session.scalars(select(MetrcTagInventory).where(MetrcTagInventory.tag_type == "package"))
        }
    assert statuses == {"RESERVED": "reserved", "USED": "used", "VOIDED": "voided"}
