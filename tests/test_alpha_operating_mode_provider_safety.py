from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.routers.alpha_integrations_status import alpha_aware_integrations
from modules.alpha_mode import AlphaOperatingModeService
from modules.coman.models import Base, Facility, Organization
from modules.integrations import IntegrationConfigurationService
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.traceability_dispatcher import TraceabilityDispatcher


ENCRYPTION_KEY = "alpha-provider-safety-encryption-key"


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    with Session(engine) as session, session.begin():
        organization = Organization(name="Alpha Provider Safety", slug="alpha-provider-safety")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Alpha Provider Facility",
            code="ALPHA-PROVIDER",
            cultivation_enabled=True,
            production_enabled=True,
        )
        session.add(facility)
        session.flush()
        return organization.id, facility.id


def _context(organization_id: str, facility_id: str) -> RequestContext:
    return RequestContext(
        user_id="alpha-admin",
        organization_id=organization_id,
        facility_id=facility_id,
        role="admin",
    )


def _queued(engine, organization_id: str, facility_id: str):
    repo = TraceabilityBackofficeRepository(engine)
    tx = repo.create_transaction(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="PKG-PRODUCTION-BLOCK",
        idempotency_key="alpha-production-block",
        actor="alpha-admin",
        license_number="LIC-PROD",
        request_payload={"quantity": -1, "unit": "g", "reason": "Test"},
    )
    tx = repo.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=tx.id,
        new_status="validated",
        actor="alpha-admin",
        reason="Validated test transaction.",
    )
    return repo.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=tx.id,
        new_status="queued",
        actor="alpha-admin",
        reason="Queued test transaction.",
    )


def test_alpha_aware_integration_status_reports_local_mode_as_provider_disabled():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    context = _context(organization_id, facility_id)
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="doobielogic_sandbox",
        actor=context.user_id,
    )

    result = alpha_aware_integrations(
        context=context,
        engine=engine,
        settings=Settings(integration_encryption_key=ENCRYPTION_KEY),
    )

    assert result["alpha_operating_mode"]["effective_mode"] == "doobielogic_sandbox"
    assert result["metrc"]["status"] == "disabled_by_alpha_mode"
    assert result["metrc"]["environment"] == "sandbox"
    assert result["metrc"]["provider_operations_enabled"] is False


def test_explicit_metrc_alpha_mode_still_reports_sandbox_before_credentials_exist():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    context = _context(organization_id, facility_id)
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="metrc_sandbox",
        actor=context.user_id,
    )

    result = alpha_aware_integrations(
        context=context,
        engine=engine,
        settings=Settings(integration_encryption_key=ENCRYPTION_KEY),
    )

    assert result["metrc"]["operating_mode"] == "metrc_sandbox"
    assert result["metrc"]["environment"] == "sandbox"
    assert result["metrc"]["provider_operations_enabled"] is False


def test_production_configured_credential_cannot_dispatch_from_metrc_sandbox_mode(monkeypatch):
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    context = _context(organization_id, facility_id)
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="metrc_sandbox",
        actor=context.user_id,
    )
    integrations = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    row = integrations.save(
        scope_type="user",
        scope_key=f"{context.user_id}|{facility_id}",
        provider="metrc",
        organization_id=organization_id,
        facility_id=facility_id,
        configuration={"state": "MA", "license_number": "LIC-PROD", "environment": "production"},
        secret="production-user-key-must-not-run",
        actor=context.user_id,
    )
    integrations.validation_result(row.id, ok=True)
    tx = _queued(engine, organization_id, facility_id)

    monkeypatch.setattr(
        "services.traceability_dispatcher.submit_metrc_action",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("alpha Metrc Sandbox must not dispatch production")),
    )
    result = TraceabilityDispatcher(
        engine,
        encryption_key=ENCRYPTION_KEY,
        metrc_integrator_api_key="production-integrator-key-must-not-run",
    ).dispatch(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=tx.id,
        actor="traceability-worker",
    )

    assert result["status"] == "reconciliation_required"
    assert result["outbound_request_sent"] is False
    attempts = TraceabilityBackofficeRepository(engine).list_attempts(
        organization_id,
        facility_id,
        tx.id,
    )
    assert attempts[-1].error_code == "alpha_mode_production_blocked"
