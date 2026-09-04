from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.routers.alpha_operating_mode import AlphaOperatingModeSave, set_mode
from backend.app.routers.alpha_sandbox_connections import alpha_aware_sandbox_connections
from modules.alpha_mode import AlphaOperatingModeService
from modules.coman.models import Base, Facility, Organization
from modules.traceability.backoffice import TraceabilityBackofficeRepository
from services.traceability_dispatcher import TraceabilityDispatcher


ROOT = Path(__file__).resolve().parents[1]


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _scope(engine):
    with Session(engine) as session, session.begin():
        organization = Organization(name="Alpha Boundary", slug="alpha-boundary")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Alpha Boundary Facility",
            code="ALPHA-BOUNDARY",
            cultivation_enabled=True,
            production_enabled=True,
            retail_enabled=True,
        )
        session.add(facility)
        session.flush()
        return organization.id, facility.id


def _context(organization_id: str, facility_id: str, role: str = "admin") -> RequestContext:
    return RequestContext(
        user_id="alpha-admin",
        organization_id=organization_id,
        facility_id=facility_id,
        role=role,
    )


def _queued_metrc_transaction(engine, organization_id: str, facility_id: str):
    repo = TraceabilityBackofficeRepository(engine)
    transaction = repo.create_transaction(
        organization_id=organization_id,
        facility_id=facility_id,
        provider="metrc",
        operation_type="package_adjustment",
        entity_type="package",
        entity_id="PKG-ALPHA-1",
        idempotency_key="alpha-mode-package-adjustment",
        actor="alpha-admin",
        license_number="LIC-ALPHA",
        request_payload={"quantity": -1, "unit": "g", "reason": "Scale Variance"},
    )
    transaction = repo.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="validated",
        actor="alpha-admin",
        reason="Validated for alpha mode test.",
    )
    return repo.transition_logged(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        new_status="queued",
        actor="alpha-admin",
        reason="Queued for alpha mode test.",
    )


def test_admin_can_switch_facility_mode_and_operator_cannot():
    engine = _engine()
    organization_id, facility_id = _scope(engine)

    saved = set_mode(
        AlphaOperatingModeSave(mode="metrc_sandbox"),
        context=_context(organization_id, facility_id),
        engine=engine,
    )
    assert saved["effective_mode"] == "metrc_sandbox"
    assert saved["explicit"] is True

    with pytest.raises(HTTPException) as exc:
        set_mode(
            AlphaOperatingModeSave(mode="doobielogic_sandbox"),
            context=_context(organization_id, facility_id, role="operator"),
            engine=engine,
        )
    assert exc.value.status_code == 403


def test_dev_provider_list_hides_metrc_card_in_doobielogic_sandbox():
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    context = _context(organization_id, facility_id, role="dev")
    settings = Settings(integration_encryption_key="alpha-test-encryption-key")
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="doobielogic_sandbox",
        actor=context.user_id,
    )

    local = alpha_aware_sandbox_connections(context=context, engine=engine, settings=settings)
    assert local["alpha_operating_mode"] == "doobielogic_sandbox"
    assert "metrc" not in local["providers"]
    assert {"dutchie", "biotrack", "quickbooks"} <= set(local["providers"])

    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="metrc_sandbox",
        actor=context.user_id,
    )
    connected = alpha_aware_sandbox_connections(context=context, engine=engine, settings=settings)
    assert connected["alpha_operating_mode"] == "metrc_sandbox"
    assert "metrc" in connected["providers"]


def test_queued_metrc_transaction_cannot_dispatch_after_switch_to_local(monkeypatch):
    engine = _engine()
    organization_id, facility_id = _scope(engine)
    AlphaOperatingModeService(engine).set_mode(
        organization_id,
        facility_id,
        mode="doobielogic_sandbox",
        actor="alpha-admin",
    )
    transaction = _queued_metrc_transaction(engine, organization_id, facility_id)

    monkeypatch.setattr(
        "services.traceability_dispatcher.submit_metrc_action",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("local alpha mode must never call Metrc")),
    )
    result = TraceabilityDispatcher(
        engine,
        encryption_key="alpha-test-encryption-key",
        metrc_integrator_api_key="should-not-be-used",
    ).dispatch(
        organization_id=organization_id,
        facility_id=facility_id,
        transaction_id=transaction.id,
        actor="traceability-worker",
    )

    assert result["ok"] is False
    assert result["status"] == "reconciliation_required"
    assert result["outbound_request_sent"] is False
    assert result["retryable"] is False
    stored = TraceabilityBackofficeRepository(engine).get_transaction(
        organization_id,
        facility_id,
        transaction.id,
    )
    assert stored.status == "reconciliation_required"
    attempts = TraceabilityBackofficeRepository(engine).list_attempts(
        organization_id,
        facility_id,
        transaction.id,
    )
    assert attempts[-1].error_code == "alpha_mode_doobielogic_sandbox"


def test_alpha_mode_ui_exposes_simple_choice_and_gates_metrc_configuration():
    source = (ROOT / "frontend" / "src" / "pages" / "IntegrationsPage.tsx").read_text(encoding="utf-8")
    assert 'apiGet<AlphaOperatingMode>("/api/v1/alpha-operating-mode"' in source
    assert 'apiPost<AlphaOperatingMode>("/api/v1/alpha-operating-mode"' in source
    assert "DoobieLogic Sandbox" in source
    assert "Metrc Sandbox" in source
    assert "Metrc is optional during alpha" in source
    assert "DoobieLogic Sandbox is active. Existing saved Metrc credentials are left encrypted in place" in source
    assert "function MetrcCard({ value, enabled, onSaved }" in source


def test_main_registers_mode_aware_dev_provider_list_before_legacy_list():
    source = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    alpha = "app.include_router(alpha_sandbox_connections_router, prefix=settings.api_prefix)"
    legacy = "app.include_router(sandbox_integrations_router, prefix=settings.api_prefix)"
    assert alpha in source and legacy in source
    assert source.index(alpha) < source.index(legacy)
