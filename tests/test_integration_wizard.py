import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.test_onboarding_reporting import setup, NOW  # noqa: F401
from backend.app.config import Settings
from backend.app.routers import adoption, integrations, native_integrations, alpha_operating_mode
from backend.app.services import metrc_context
from backend.app.services.integration_wizard import wizard
from backend.app.services.adoption_models import ReadinessAnnotation
from modules.coman.models import Facility, Product
from modules.integrations.accounting_links import AccountingSyncLink


@pytest.fixture
def state(setup, monkeypatch):
    engine, context = setup
    AccountingSyncLink.__table__.create(engine)
    public = {"configured": True, "status": "configured", "last_validated_at": None,
              "secret_hint": "DO-NOT-EXPOSE", "configuration": {"environment": "sandbox", "secret": "DO-NOT-EXPOSE"}}
    values = {key: dict(public) for key in ("metrc", "biotrack", "quickbooks", "spacemail", "ai_runtime", "doobie")}
    mode = {"effective_mode": "metrc_sandbox", "message": "Sandbox only"}
    metrc = Mock(configured=True, trusted_mapping=True, environment="sandbox")
    monkeypatch.setattr(integrations, "integrations", lambda *_: values)
    monkeypatch.setattr(native_integrations, "native_integrations", lambda *_: values)
    monkeypatch.setattr(alpha_operating_mode, "current_mode", lambda *_: mode)
    monkeypatch.setattr(metrc_context, "resolve_metrc_context", lambda *_: (None, metrc))
    return engine, context, values, mode, metrc


def snapshot(state, context=None):
    return wizard(state[0], Settings(), context or state[1])


def item(state, key):
    return next(item for item in snapshot(state)["items"] if item["key"] == key)


def test_evidence_not_credentials_and_secret_non_disclosure(state):
    assert item(state, "metrc")["status"] == "needs_validation"
    assert "DO-NOT-EXPOSE" not in json.dumps(snapshot(state), default=str)
    state[2]["metrc"]["status"] = "connected"
    assert item(state, "metrc")["status"] == "needs_validation"
    state[2]["metrc"]["last_validated_at"] = NOW
    assert item(state, "metrc")["status"] == "connected"
    state[4].trusted_mapping = False
    assert item(state, "metrc")["status"] == "needs_mapping"
    state[4].configured = False
    assert item(state, "metrc")["status"] == "blocked"
    assert item(state, "metrc")["test_path"] is None


def test_resume_skip_is_durable_scoped_and_cannot_complete_required(state):
    engine, context, *_ = state
    adoption.wizard_progress(adoption.WizardProgress(step="map"), context, engine)
    adoption.wizard_choice("quickbooks", adoption.WizardChoice(skipped=True), context, engine, Settings())
    assert snapshot(state)["step"] == "map"
    assert item(state, "quickbooks")["status"] == "optional_skipped"
    other = replace(context, facility_id="two")
    assert snapshot(state, other)["step"] == "facility"
    assert next(i for i in snapshot(state, other)["items"] if i["key"] == "quickbooks")["status"] == "needs_validation"
    with pytest.raises(HTTPException) as error:
        snapshot(state, replace(context, organization_id="other"))
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        adoption.wizard_choice("metrc", adoption.WizardChoice(skipped=True), context, engine, Settings())
    assert error.value.status_code == 422
    adoption.wizard_choice("quickbooks", adoption.WizardChoice(skipped=False), context, engine, Settings())
    assert item(state, "quickbooks")["status"] == "needs_validation"
    with Session(engine) as session:
        assert session.query(ReadinessAnnotation).count() == 2


def test_failed_validation_and_unavailable_provider_never_complete(state, monkeypatch):
    state[2]["biotrack"].update(status="failed", last_validated_at=NOW)
    assert item(state, "biotrack")["status"] == "blocked"
    monkeypatch.setattr(native_integrations, "native_integrations", Mock(side_effect=HTTPException(503, "private diagnostic")))
    assert item(state, "quickbooks")["status"] == "blocked"
    assert "private diagnostic" not in json.dumps(snapshot(state), default=str)


def test_mode_change_reactivates_required_provider_and_capabilities(state):
    state[3]["effective_mode"] = "doobielogic_sandbox"
    assert item(state, "metrc")["status"] == "not_applicable"
    adoption.wizard_choice("metrc", adoption.WizardChoice(skipped=True), state[1], state[0], Settings())
    state[3]["effective_mode"] = "metrc_sandbox"
    assert item(state, "metrc")["required"]
    assert item(state, "metrc")["status"] == "needs_validation"
    with Session(state[0]) as session:
        session.get(Facility, "one").commercial_enabled = False
        session.commit()
    assert item(state, "quickbooks")["status"] == "not_applicable"


def test_quickbooks_mapping_scope_and_blockers(state):
    engine, *_ = state
    state[2]["quickbooks"].update(status="connected", last_validated_at=NOW)
    with Session(engine) as session:
        session.add(Product(id="p", organization_id="org", name="Product", sku="p", item_type="cannabis"))
        session.flush()
        session.add(AccountingSyncLink(organization_id="org", facility_id="two", entity_type="item", internal_id="p", external_id="qbo-p", updated_by="admin"))
        session.commit()
    assert item(state, "quickbooks")["status"] == "needs_mapping"
    assert item(state, "quickbooks")["managed_entities"] == ["customer", "invoice"]
    with Session(engine) as session:
        session.add(AccountingSyncLink(organization_id="org", facility_id="one", entity_type="item", internal_id="p", external_id="qbo-p", updated_by="admin"))
        session.commit()
    assert item(state, "quickbooks")["status"] == "connected"
    with Session(engine) as session:
        row = session.query(AccountingSyncLink).filter_by(facility_id="one").one()
        row.status = "failed"
        session.commit()
    assert item(state, "quickbooks")["status"] == "blocked"


def test_readiness_reuses_wizard_evidence_and_permissions(state):
    result = adoption.get_readiness(state[1], state[0], Settings())
    assert next(i for i in result["items"] if i["key"] == "wizard_metrc")["status"] == "needs_validation"
    assert next(i for i in result["items"] if i["key"] == "traceability")["status"] != "complete"
    with pytest.raises(HTTPException):
        adoption.admin(replace(state[1], role="read_only"))
    state[2]["spacemail"] = None
    assert item(state, "spacemail")["test_path"] is None
    assert "DEV operator" in item(state, "spacemail")["evidence"]


def test_summary_queries_are_bounded(state):
    with Session(state[0]) as session:
        session.add_all(Product(organization_id="org", name="Product", sku=f"p-{i}", item_type="cannabis") for i in range(250))
        session.commit()
    statements = []
    def capture(*args):
        statements.append(args[2])
    event.listen(state[0], "before_cursor_execute", capture)
    try:
        assert item(state, "quickbooks")["missing_item_mappings"] == 250
    finally:
        event.remove(state[0], "before_cursor_execute", capture)
    assert len(statements) == 4


def test_wizard_api_authorization_and_scope(state):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.auth import get_request_context
    from backend.app.database import get_engine
    from backend.app.config import get_settings
    app = FastAPI()
    app.include_router(adoption.router)
    app.dependency_overrides[get_engine] = lambda: state[0]
    app.dependency_overrides[get_settings] = lambda: Settings()
    app.dependency_overrides[get_request_context] = lambda: replace(state[1], role="read_only")
    with TestClient(app) as client:
        assert client.get("/integration-wizard").status_code == 200
        assert client.post("/integration-wizard/progress", json={"step": "summary"}).status_code == 403
        assert client.post("/integration-wizard/providers/quickbooks", json={"skipped": True}).status_code == 403
        app.dependency_overrides[get_request_context] = lambda: replace(state[1], organization_id="foreign")
        assert client.get("/integration-wizard").status_code == 404
        assert client.post("/integration-wizard/progress", json={"step": "summary"}).status_code == 404
        app.dependency_overrides[get_request_context] = lambda: state[1]
        assert client.post("/integration-wizard/providers/invented", json={"skipped": True}).status_code == 404
        assert client.post("/integration-wizard/progress", json={"step": "invented"}).status_code == 422


def test_real_configuration_contracts_preserve_scope_and_hide_credentials(setup):
    from modules.alpha_mode.models import AlphaOperatingMode
    from modules.regulatory.models import RegulatoryFacilityMapping
    from modules.integrations import IntegrationConfigurationService
    engine, context = setup
    for model in (AccountingSyncLink, AlphaOperatingMode, RegulatoryFacilityMapping):
        model.__table__.create(engine)
    settings = Settings(integration_encryption_key="synthetic-wizard-test-encryption")
    service = IntegrationConfigurationService(engine, settings.integration_encryption_key)
    row = service.save(scope_type="facility", scope_key="one", provider="quickbooks", organization_id="org",
        facility_id="one", actor="admin", secret="synthetic-private-refresh-token", configuration={"environment": "sandbox", "realm_id": "company-one"})
    result = wizard(engine, settings, context)
    assert next(i for i in result["items"] if i["key"] == "quickbooks")["status"] == "needs_validation"
    assert next(i for i in result["items"] if i["key"] == "metrc")["status"] == "not_applicable"
    service.validation_result(row.id, ok=True)
    result = wizard(engine, settings, context)
    assert next(i for i in result["items"] if i["key"] == "quickbooks")["status"] == "connected"
    assert "synthetic-private-refresh-token" not in json.dumps(result, default=str)
    assert "secret_hint" not in json.dumps(result, default=str)
    other = wizard(engine, settings, replace(context, facility_id="two"))
    assert next(i for i in other["items"] if i["key"] == "quickbooks")["status"] == "needs_validation"
    service.validation_result(row.id, ok=False, error="synthetic-private-refresh-token")
    result = wizard(engine, settings, context)
    assert next(i for i in result["items"] if i["key"] == "quickbooks")["status"] == "blocked"
    assert "synthetic-private-refresh-token" not in json.dumps(result, default=str)
