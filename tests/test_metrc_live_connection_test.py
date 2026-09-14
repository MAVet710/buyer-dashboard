from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.routers.alpha_sandbox_connections import alpha_test_metrc_sandbox_connection
from backend.app.services.metrc_context import metrc_sandbox_scope_key, metrc_scope_key
from modules.alpha_mode import AlphaOperatingModeService
from modules.coman.models import Base, Facility, Organization
from modules.integrations import IntegrationConfigurationService


ENCRYPTION_KEY = "metrc-live-test-encryption"


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="One", slug="one"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="MA Sandbox", code="MASBX"))
        session.commit()
    return engine


def _context() -> RequestContext:
    return RequestContext(user_id="dev-1", organization_id="org-1", facility_id="fac-1", role="dev")


def _configured_scope(engine):
    context = _context()
    AlphaOperatingModeService(engine).set_mode(
        context.organization_id,
        context.facility_id,
        mode="metrc_sandbox",
        actor=context.user_id,
    )
    service = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    service.save(
        scope_type="facility",
        scope_key=metrc_sandbox_scope_key(context),
        provider="metrc_sandbox",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={"state": "MA", "license_number": "LIC-1", "environment": "sandbox"},
        secret="v",
        actor=context.user_id,
    )
    service.save(
        scope_type="user",
        scope_key=metrc_scope_key(context),
        provider="metrc",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={"state": "MA", "license_number": "LIC-1", "environment": "sandbox"},
        secret="u",
        actor=context.user_id,
    )
    return context


def test_metrc_test_connection_uses_exact_scoped_pair_and_normal_facilities_read(monkeypatch):
    engine = _engine()
    context = _configured_scope(engine)
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "http_status": 200,
            "records": [
                {
                    "provider": "metrc",
                    "resource": "facilities",
                    "source": {"Id": 6704, "Name": "MA Sandbox 4", "LicenseNumber": "LIC-1"},
                }
            ],
        }

    monkeypatch.setattr("backend.app.routers.alpha_sandbox_connections.fetch_metrc_resource", fake_fetch)
    result = alpha_test_metrc_sandbox_connection(
        context=context,
        engine=engine,
        settings=Settings(integration_encryption_key=ENCRYPTION_KEY),
    )

    assert captured["state"] == "MA"
    assert captured["environment"] == "sandbox"
    assert captured["resource"] == "facilities"
    assert captured["integrator_api_key"] == "v"
    assert captured["user_api_key"] == "u"
    assert captured["max_attempts"] == 1
    assert result["result"]["connected"] is True
    assert result["result"]["verified"] is True
    assert result["result"]["license_mapping_verified"] is True
    assert result["result"]["matched_facility_count"] == 1
    assert result["result"]["network_request_sent"] is True
    assert result["result"]["read_only"] is True


def test_metrc_test_connection_surfaces_provider_401_without_retry_or_write(monkeypatch):
    engine = _engine()
    context = _configured_scope(engine)
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return {
            "ok": False,
            "http_status": 401,
            "status": "auth_failed",
            "message": "Metrc rejected the saved API keys.",
        }

    monkeypatch.setattr("backend.app.routers.alpha_sandbox_connections.fetch_metrc_resource", fake_fetch)
    result = alpha_test_metrc_sandbox_connection(
        context=context,
        engine=engine,
        settings=Settings(integration_encryption_key=ENCRYPTION_KEY),
    )

    assert captured["resource"] == "facilities"
    assert captured["max_attempts"] == 1
    assert result["result"]["provider_http_status"] == 401
    assert result["result"]["connected"] is False
    assert result["result"]["verified"] is False
    assert result["result"]["network_request_sent"] is True
    assert result["result"]["read_only"] is True


def test_metrc_live_test_route_precedes_legacy_configuration_only_test():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    main = (root / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    alpha = "app.include_router(alpha_sandbox_connections_router, prefix=settings.api_prefix)"
    legacy = "app.include_router(sandbox_integrations_router, prefix=settings.api_prefix)"
    assert main.index(alpha) < main.index(legacy)

    source = (root / "backend" / "app" / "routers" / "alpha_sandbox_connections.py").read_text(encoding="utf-8")
    assert '@sandbox_router.post("/metrc/test")' in source
    assert 'resource="facilities"' in source
    assert "max_attempts=1" in source
