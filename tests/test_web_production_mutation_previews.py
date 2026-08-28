from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, Organization, ProductionOrder
from modules.production_erp.models import ProductionCostEvent


def _fixture():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(id="org-preview", name="Preview Org", slug="preview-org")
        facility = Facility(
            id="facility-preview",
            organization_id=organization.id,
            name="Production Preview",
            code="PROD-PREVIEW",
            production_enabled=True,
            retail_enabled=False,
        )
        order = ProductionOrder(
            id="order-preview",
            organization_id=organization.id,
            facility_id=facility.id,
            order_number="RUN-PREVIEW-1",
            work_type="internal",
            product_name="Preview Finished Good",
            sku="PREVIEW-FG",
            product_format="finished good",
            requested_units=100,
            priority="normal",
            status="in_progress",
            notes="",
            created_by="seed",
            updated_by="seed",
        )
        session.add_all([organization, facility, order])
        session.commit()
    return engine


def _headers(role="dev"):
    return {
        "X-Organization-Id": "org-preview",
        "X-Facility-Id": "facility-preview",
        "X-User-Id": "preview-user",
        "X-User-Role": role,
    }


def test_production_mutation_api_requires_fresh_preview_before_commit():
    engine = _fixture()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    payload = {
        "action_type": "cost_event",
        "payload": {
            "category": "labor",
            "amount_usd": 25,
            "quantity": 1,
            "unit": "hr",
            "source_type": "manual",
            "source_id": "",
            "notes": "Preview API test",
        },
    }
    try:
        preview = client.post(
            "/api/v1/production/orders/order-preview/mutations/preview",
            headers=_headers(),
            json=payload,
        )
        assert preview.status_code == 200, preview.text
        preview_key = preview.json()["preview_key"]
        assert preview.json()["details"]["cogs_before"] == 0
        assert preview.json()["details"]["cogs_after"] == 25

        with Session(engine) as session:
            session.add(
                ProductionCostEvent(
                    organization_id="org-preview",
                    facility_id="facility-preview",
                    production_order_id="order-preview",
                    category="labor",
                    amount_usd=10,
                    source_type="manual",
                    source_id="concurrent",
                    notes="Concurrent cost",
                    actor="other-user",
                )
            )
            session.commit()

        stale = client.post(
            "/api/v1/production/orders/order-preview/mutations/commit",
            headers=_headers(),
            json={**payload, "preview_key": preview_key},
        )
        assert stale.status_code == 422, stale.text
        assert "stale" in stale.json()["detail"].casefold()

        fresh = client.post(
            "/api/v1/production/orders/order-preview/mutations/preview",
            headers=_headers(),
            json=payload,
        )
        assert fresh.status_code == 200, fresh.text
        applied = client.post(
            "/api/v1/production/orders/order-preview/mutations/commit",
            headers=_headers(),
            json={**payload, "preview_key": fresh.json()["preview_key"]},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["status"] == "applied"
        assert applied.json()["result"]["amount_usd"] == 25
    finally:
        app.dependency_overrides.clear()


def test_production_mutation_api_preserves_qa_role_guard():
    engine = _fixture()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    try:
        denied = client.post(
            "/api/v1/production/orders/order-preview/mutations/preview",
            headers=_headers("operator"),
            json={
                "action_type": "qa_decision",
                "payload": {"event_type": "hold", "result": "pending", "output_id": None},
            },
        )
        assert denied.status_code == 403, denied.text
        assert "cannot post QA decisions" in denied.json()["detail"]
    finally:
        app.dependency_overrides.clear()
