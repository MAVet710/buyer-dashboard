from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Base
from services.demo_data import build_demo_payload
from services.web_parity import run_web_parity


def test_representative_facility_has_durable_streamlit_to_fastapi_parity():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    seeded = ensure_coman_demo_dataset(state={}, actor="parity-test", payload=build_demo_payload(date(2026, 8, 21), scale="small"), engine=engine)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": seeded["organization_id"], "X-Facility-Id": seeded["facility_id"], "X-User-Id": "parity-test", "X-User-Role": "dev"}

    def get_json(path: str):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)
        return response.json()

    try:
        report = run_web_parity(engine, seeded["organization_id"], seeded["facility_id"], get_json)
    finally:
        app.dependency_overrides.clear()
    assert report["passed"] is True, report["checks"]
    assert report["failed_count"] == 0
    assert report["check_count"] >= 20
