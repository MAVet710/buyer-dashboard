from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility
from modules.coman.repository import ComanRepository


def _engine():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _scope(engine):
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    organization = repo.create_organization("Extraction Stage Atomicity")
    facility = repo.create_facility(organization.id, "Manufacturing", "EXT-ATOMIC")
    with Session(engine) as session, session.begin():
        row = session.get(Facility, facility.id)
        assert row is not None
        row.production_enabled = True
        row.license_number = "MP281235"
        row.license_type = "Marijuana Product Manufacturer"
    return organization, facility


def test_invalid_stage_enhancement_leaves_no_event_or_run_state_change():
    engine = _engine()
    organization, facility = _scope(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": organization.id,
        "X-Facility-Id": facility.id,
        "X-User-Id": "extraction-operator",
        "X-User-Role": "dev",
    }
    client = TestClient(app, raise_server_exceptions=False)
    try:
        created = client.post(
            "/api/v1/extraction/runs",
            headers=headers,
            json={
                "batch_number": "EXT-STAGE-ATOMIC-001",
                "workflow_key": "ethanol_crude",
                "method": "Ethanol",
                "product_family": "Vape Oil",
            },
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        before = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
        assert before.status_code == 200, before.text
        before_payload = before.json()
        before_event_ids = [row["id"] for row in before_payload["events"]]
        before_run = before_payload["run"]

        rejected = client.post(
            f"/api/v1/extraction/runs/{run_id}/events",
            headers=headers,
            json={
                "stage_key": "formulation",
                "event_type": "measurement",
                "output_weight_g": 105,
                "stage_output_field": "distillate_output_g",
                "formulation_used": True,
                "formulation_base_g": 100,
                "terpene_handling_mode": "Reintroduced Cannabis Terpenes",
                "terpene_percentage": 5,
            },
        )
        assert rejected.status_code == 422, rejected.text
        assert "Stage output field is not valid for this workflow stage" in rejected.text

        after = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
        assert after.status_code == 200, after.text
        after_payload = after.json()
        assert [row["id"] for row in after_payload["events"]] == before_event_ids
        assert after_payload["run"]["current_stage_key"] == before_run["current_stage_key"]
        assert after_payload["run"]["status"] == before_run["status"]
        assert after_payload["run"]["final_output_g"] == before_run["final_output_g"]
    finally:
        app.dependency_overrides.clear()


def test_invalid_stage_formulation_leaves_no_event_or_run_state_change():
    engine = _engine()
    organization, facility = _scope(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": organization.id,
        "X-Facility-Id": facility.id,
        "X-User-Id": "extraction-formulator",
        "X-User-Role": "dev",
    }
    client = TestClient(app, raise_server_exceptions=False)
    try:
        created = client.post(
            "/api/v1/extraction/runs",
            headers=headers,
            json={
                "batch_number": "EXT-STAGE-ATOMIC-002",
                "workflow_key": "ethanol_crude",
                "method": "Ethanol",
                "product_family": "Vape Oil",
            },
        )
        assert created.status_code == 201, created.text
        run_id = created.json()["id"]

        before = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
        assert before.status_code == 200, before.text
        before_payload = before.json()
        before_event_ids = [row["id"] for row in before_payload["events"]]
        before_run = before_payload["run"]

        rejected = client.post(
            f"/api/v1/extraction/runs/{run_id}/events",
            headers=headers,
            json={
                "stage_key": "formulation",
                "event_type": "measurement",
                "formulation_used": True,
                "formulation_base_g": 100,
                "terpene_handling_mode": "Reintroduced Cannabis Terpenes",
                "terpene_percentage": 25,
            },
        )
        assert rejected.status_code == 422, rejected.text
        assert "outside the supported formulation range" in rejected.text

        after = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
        assert after.status_code == 200, after.text
        after_payload = after.json()
        assert [row["id"] for row in after_payload["events"]] == before_event_ids
        assert after_payload["run"]["current_stage_key"] == before_run["current_stage_key"]
        assert after_payload["run"]["status"] == before_run["status"]
        assert after_payload["run"]["final_output_g"] == before_run["final_output_g"]
    finally:
        app.dependency_overrides.clear()
