import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, Facility, Organization
from modules.integrations.models import (
    IntegrationConfiguration,
    IntegrationSyncAttempt,
    IntegrationSyncRecord,
    IntegrationSyncState,
)
from modules.integrations.sandbox_runtime import SandboxIntegrationRuntime, sanitize
from modules.integrations.service import IntegrationConfigurationService


ENCRYPTION_KEY = "sandbox-runtime-test-encryption-key"


def _runtime_fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    AuditEvent.__table__.create(engine)
    IntegrationConfiguration.__table__.create(engine)
    IntegrationSyncState.__table__.create(engine)
    IntegrationSyncRecord.__table__.create(engine)
    IntegrationSyncAttempt.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        session.add(Organization(id="org-sandbox", name="DEV Sandbox", slug="dev-sandbox"))
        session.add(Facility(id="fac-sandbox", organization_id="org-sandbox", name="Sandbox Facility", code="SANDBOX"))
        session.add(Organization(id="org-other", name="Other Org", slug="other-org"))
        session.add(Facility(id="fac-other", organization_id="org-other", name="Other Facility", code="OTHER"))
    return engine, sessions


def _save_dutchie(engine, *, environment="sandbox"):
    service = IntegrationConfigurationService(engine, ENCRYPTION_KEY)
    service.save(
        scope_type="facility",
        scope_key="org-sandbox:fac-sandbox:sandbox",
        provider="dutchie_sandbox",
        organization_id="org-sandbox",
        facility_id="fac-sandbox",
        configuration={"environment": environment, "location_id": "sandbox-location"},
        secret="sandbox-secret-value",
        actor="developer",
    )
    return service


def test_sandbox_runtime_syncs_all_resources_and_deduplicates_replays():
    engine, sessions = _runtime_fixture()
    _save_dutchie(engine)
    runtime = SandboxIntegrationRuntime(engine, ENCRYPTION_KEY)

    first = runtime.sync(
        organization_id="org-sandbox",
        facility_id="fac-sandbox",
        provider="dutchie",
        actor="developer",
    )
    assert first["environment"] == "sandbox"
    assert first["production_writes_enabled"] is False
    assert first["transport"] == "deterministic_fixture"
    assert {item["resource"] for item in first["resources"]} == {"sales", "inventory", "catalog"}
    assert first["totals"] == {"records": 9, "accepted": 9, "duplicates": 0, "errors": 0}

    second = runtime.sync(
        organization_id="org-sandbox",
        facility_id="fac-sandbox",
        provider="dutchie",
        actor="developer",
    )
    assert second["totals"] == {"records": 9, "accepted": 0, "duplicates": 9, "errors": 0}

    status = runtime.status(
        organization_id="org-sandbox",
        facility_id="fac-sandbox",
        provider="dutchie",
    )
    assert status["adapter_contract_ready"] is True
    assert status["production_writes_enabled"] is False
    assert {state["resource"] for state in status["states"]} == {"sales", "inventory", "catalog"}
    assert all(state["cursor"] == "fixture-v1" for state in status["states"])
    assert all(state["status"] == "succeeded" for state in status["states"])

    with sessions() as session:
        records = list(session.scalars(select(IntegrationSyncRecord)))
        attempts = list(session.scalars(select(IntegrationSyncAttempt)))
    assert len(records) == 9
    assert len(attempts) == 6
    assert all(record.provider == "dutchie_sandbox" for record in records)
    assert all("sandbox-secret-value" not in record.raw_payload_json for record in records)
    sale = next(record for record in records if record.resource == "sales")
    assert "source_record_id" in json.loads(sale.normalized_payload_json)["sale"]


def test_runtime_redacts_credentials_before_raw_staging():
    cleaned = sanitize(
        {
            "UserApiKey": "user-key",
            "authorization": "Bearer secret",
            "nested": {"client_secret": "client-secret", "name": "safe"},
        }
    )
    assert cleaned["UserApiKey"] == "[REDACTED]"
    assert cleaned["authorization"] == "[REDACTED]"
    assert cleaned["nested"]["client_secret"] == "[REDACTED]"
    assert cleaned["nested"]["name"] == "safe"


def test_runtime_rejects_cross_tenant_and_non_sandbox_configuration():
    engine, _ = _runtime_fixture()
    service = _save_dutchie(engine)
    runtime = SandboxIntegrationRuntime(engine, ENCRYPTION_KEY)

    with pytest.raises(ValueError, match="outside the active organization"):
        runtime.sync(
            organization_id="org-sandbox",
            facility_id="fac-other",
            provider="dutchie",
            actor="developer",
        )

    service.save(
        scope_type="facility",
        scope_key="org-sandbox:fac-sandbox:sandbox",
        provider="dutchie_sandbox",
        organization_id="org-sandbox",
        facility_id="fac-sandbox",
        configuration={"environment": "production", "location_id": "should-not-run"},
        secret=None,
        actor="developer",
    )
    with pytest.raises(ValueError, match="refuses non-sandbox"):
        runtime.sync(
            organization_id="org-sandbox",
            facility_id="fac-sandbox",
            provider="dutchie",
            actor="developer",
        )


def test_provider_adapter_contracts_cover_phase_resources():
    engine, _ = _runtime_fixture()
    runtime = SandboxIntegrationRuntime(engine, ENCRYPTION_KEY)
    expected = {
        "metrc": {"packages", "transfers", "items"},
        "dutchie": {"sales", "inventory", "catalog"},
        "biotrack": {"inventory", "transfers", "plants"},
        "quickbooks": {"invoices", "payments", "items"},
    }
    for provider, resources in expected.items():
        capabilities = runtime.capabilities(provider)
        assert set(capabilities["resources"]) == resources
        assert capabilities["read_mode"] == "deterministic_fixture"
        assert capabilities["production_writes_enabled"] is False
