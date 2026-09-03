from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.services.metrc_context import metrc_sandbox_scope_key, metrc_scope_key, resolve_metrc_context
from modules.coman.models import Base, Facility, Organization
from modules.integrations import IntegrationConfigurationService


ENCRYPTION_KEY = "metrc-fastapi-wiring-test"


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="One", slug="one"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Sandbox", code="SBX"))
        session.commit()
    return engine


def _context() -> RequestContext:
    return RequestContext(user_id="dev-1", organization_id="org-1", facility_id="fac-1", role="dev")


def _save_sandbox_vendor(service: IntegrationConfigurationService, context: RequestContext, secret: str = "vendor-key"):
    return service.save(
        scope_type="facility",
        scope_key=metrc_sandbox_scope_key(context),
        provider="metrc_sandbox",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={
            "state": "MA",
            "license_number": "MA-SANDBOX-LIC",
            "base_url": "https://sandbox-api-MA.metrc.com",
            "environment": "sandbox",
        },
        secret=secret,
        actor=context.user_id,
    )


def _save_user_key(service: IntegrationConfigurationService, context: RequestContext, secret: str):
    return service.save(
        scope_type="user",
        scope_key=metrc_scope_key(context),
        provider="metrc",
        organization_id=context.organization_id,
        facility_id=context.facility_id,
        configuration={"state": "MA", "license_number": "MA-SANDBOX-LIC", "environment": "production"},
        secret=secret,
        actor=context.user_id,
    )


def test_saved_sandbox_connection_supplies_integrator_key_without_server_env_secret():
    engine = _engine()
    context = _context()
    service = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    _save_sandbox_vendor(service, context)
    _save_user_key(service, context, "user-key")

    _, metrc = resolve_metrc_context(engine, Settings(integration_encryption_key=ENCRYPTION_KEY), context)

    assert metrc.integrator_api_key == "vendor-key"
    assert metrc.user_api_key == "user-key"
    assert metrc.environment == "sandbox"
    assert metrc.state == "MA"
    assert metrc.license_number == "MA-SANDBOX-LIC"
    assert metrc.configured is True
    assert "Streamlit" not in metrc.message


def test_legacy_single_key_misclassification_fails_closed_as_missing_user_key():
    engine = _engine()
    context = _context()
    service = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    _save_sandbox_vendor(service, context, "vendor-key")
    _save_user_key(service, context, "vendor-key")

    _, metrc = resolve_metrc_context(engine, Settings(integration_encryption_key=ENCRYPTION_KEY), context)

    assert metrc.integrator_api_key == "vendor-key"
    assert metrc.user_api_key == ""
    assert metrc.environment == "sandbox"
    assert metrc.configured is False
    assert "distinct Metrc user API key" in metrc.message


def test_sandbox_vendor_key_is_discoverable_even_before_user_key_is_saved():
    engine = _engine()
    context = _context()
    service = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    _save_sandbox_vendor(service, context)

    _, metrc = resolve_metrc_context(engine, Settings(integration_encryption_key=ENCRYPTION_KEY), context)

    assert metrc.integrator_api_key == "vendor-key"
    assert metrc.user_api_key == ""
    assert metrc.environment == "sandbox"
    assert metrc.configured is False
    assert "user API key is still required" in metrc.message
