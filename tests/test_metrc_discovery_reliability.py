from types import SimpleNamespace

import pytest
import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from backend.app.auth import RequestContext
from backend.app.observability import install_observability
from backend.app.routers import sandbox_integrations as routes
from modules.coman.models import Base, Facility, Organization
from modules.integrations import IntegrationConfigurationService
from modules.integrations.models import IntegrationSyncRecord
from services.metrc_client import fetch_metrc_resource
from services.metrc_facility_bootstrap import MetrcFacilityBootstrapService


@pytest.fixture
def setup():
    # A single connection exposes leaked/nested sessions masked by SQLite's
    # usual test pool. No production database or provider is accessed.
    engine = create_engine("sqlite://", poolclass=QueuePool, pool_size=1,
                           max_overflow=0, pool_timeout=0.1)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Test", slug="test", active=True)
        session.add(org)
        session.flush()
        facility = Facility(organization_id=org.id, name="Bootstrap", code="BOOT", active=True,
                            license_number="BOOT")
        session.add(facility)
        session.flush()
        context = RequestContext("tester", org.id, facility.id, "dev", "Uploads")
    settings = SimpleNamespace(integration_encryption_key="test-only")
    service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
    for provider, scope_type, key in (
        ("metrc", "user", f"tester|{context.facility_id}"),
        ("metrc_sandbox", "facility", f"{context.organization_id}:{context.facility_id}:sandbox"),
    ):
        service.save(scope_type=scope_type, scope_key=key, provider=provider,
                     organization_id=context.organization_id, facility_id=context.facility_id,
                     configuration={"state": "MA", "environment": "sandbox", "license_number": "BOOT"},
                     secret=f"test-{provider}", actor="tester")
    yield engine, context, settings, service
    assert engine.pool.checkedout() == 0
    engine.dispose()


def discover(monkeypatch, setup):
    engine, context, settings, _ = setup

    def fetch(**kwargs):
        assert engine.pool.checkedout() == 0
        assert kwargs["max_attempts"] == 1
        return {"ok": True, "records": [{"source": {
            "Id": 1, "Name": "Discovered", "License": {"Number": "MP-TEST"},
            "Permissions": ["test-permission"],
        }}]}

    monkeypatch.setattr(routes, "fetch_metrc_resource", fetch)
    monkeypatch.setattr(MetrcFacilityBootstrapService, "sync",
                        lambda *args, **kwargs: pytest.fail("Discovery must not run the full sync"))
    return routes.discover_metrc_sandbox_facilities(context, engine, settings)


def test_discovery_returns_mappings_without_inline_provider_fanout(monkeypatch, setup):
    engine, _, _, _ = setup
    result = discover(monkeypatch, setup)
    assert result["facilities"][0]["sync_status"] == "pending"
    assert result["auto_created"] == 1
    with Session(engine) as session:
        profile = session.scalar(select(IntegrationSyncRecord).where(IntegrationSyncRecord.resource == "facility_profile"))
        assert "test-permission" in profile.raw_payload_json
    repeated = discover(monkeypatch, setup)
    assert repeated["auto_created"] == 0
    assert repeated["auto_linked"] == 1


def test_bootstrap_checks_organization_and_credential_scope(monkeypatch, setup):
    engine, context, settings, _ = setup
    row = discover(monkeypatch, setup)["facilities"][0]
    payload = routes.MetrcFacilitySync(facility_id=row["doobielogic_facility"]["id"], license_number=row["license_number"])
    calls = []

    def sync(self, **kwargs):
        assert engine.pool.checkedout() == 0
        calls.append(kwargs)
        return {"totals": {"failed": 0, "records": 0}}

    monkeypatch.setattr(MetrcFacilityBootstrapService, "sync", sync)
    assert routes.bootstrap_metrc_sandbox_facility(payload, context, engine, settings)["ok"]
    assert calls[0]["environment"] == "sandbox"
    other = RequestContext("tester", "other-org", context.facility_id, "dev", "Uploads")
    with pytest.raises(HTTPException) as error:
        routes.bootstrap_metrc_sandbox_facility(payload, other, engine, settings)
    assert error.value.status_code == 404
    assert len(calls) == 1


def test_metrc_401_does_not_trigger_app_login_refresh(monkeypatch, setup):
    _, context, _, service = setup
    monkeypatch.setattr(routes, "fetch_metrc_resource", lambda **kwargs: {
        "ok": False, "http_status": 401, "message": "Metrc rejected the integrator/user API key pair.",
    })
    with pytest.raises(HTTPException) as error:
        routes._fetch_metrc_facilities(service, context)
    assert error.value.status_code == 502
    assert "Metrc rejected" in error.value.detail


def test_profile_pool_exhaustion_stops_after_first_facility(monkeypatch, setup):
    engine, context, _, service = setup
    calls = []

    def busy(*args, **kwargs):
        calls.append(kwargs)
        raise PoolTimeout()

    monkeypatch.setattr(MetrcFacilityBootstrapService, "_persist", busy)
    rows = [{"status": "linked", "license_number": str(i), "doobielogic_facility": {"id": str(i)}} for i in range(5)]
    records = [{"License": {"Number": str(i)}} for i in range(5)]
    with pytest.raises(PoolTimeout):
        routes._bootstrap_bound_facilities(discovery={"facilities": rows}, records=records,
            vendor=None, user=None, service=service, context=context, engine=engine)
    assert len(calls) == 1


def test_interactive_reads_can_disable_transport_retries(monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout()

    monkeypatch.setattr("services.metrc_client.requests.get", timeout)
    result = fetch_metrc_resource(state="MA", user_api_key="user", integrator_api_key="vendor",
                                  resource="facilities", environment="sandbox", max_attempts=1)
    assert result["status"] == "timeout"
    assert len(calls) == 1


def test_bootstrap_deduplication_uses_one_lookup_not_one_per_record(setup):
    engine, context, _, _ = setup
    selects = []

    def capture(conn, cursor, statement, params, execution_context, many):
        if statement.lstrip().upper().startswith("SELECT") and "integration_sync_records" in statement:
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    service = MetrcFacilityBootstrapService(engine)
    records = [{"Id": i} for i in range(100)]
    arguments = dict(organization_id=context.organization_id, facility_id=context.facility_id,
                     resource="items", environment="sandbox", actor="tester", transport="test",
                     records=records + [records[0]])
    first = service._persist(**arguments)
    second = service._persist(**arguments)
    assert len(selects) == 2
    assert first["accepted_count"] == 100 and first["duplicate_count"] == 1
    assert second["accepted_count"] == 0 and second["duplicate_count"] == 101


def test_pool_exhaustion_returns_actionable_503_not_generic_500():
    app = FastAPI()
    install_observability(app)

    @app.get("/busy")
    def busy():
        raise PoolTimeout("internal connection details must not be returned")

    with TestClient(app) as client:
        response = client.get("/busy")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json()["error"]["code"] == "database_busy"
    assert "internal connection" not in response.text
