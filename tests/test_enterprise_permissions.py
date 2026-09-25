import asyncio
import importlib
import inspect
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.permissions import PERMISSION_REGISTRY, ROLE_DEFAULTS, permission_snapshot
from backend.app.routers.admin_user_create import (
    UserPermissionUpdate, permission_registry, security_readiness, update_user_permissions,
)
from modules.coman.models import Base, AppUser, AppUserFacilityRole, AuditEvent, Facility, Organization
from modules.coman.permissions import AppUserPermissionOverride


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[model.__table__ for model in
        (Organization, Facility, AppUser, AppUserFacilityRole, AuditEvent, AppUserPermissionOverride)])
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org", name="Test", slug="test"))
        session.add_all([Facility(id=f, organization_id="org", name=f, code=f) for f in ("a", "b")])
        session.add(AppUser(id="actor", organization_id="org", username="actor", normalized_username="actor", role="admin", password_hash="test-only"))
        session.add(AppUser(id="target", organization_id="org", username="target", normalized_username="target", role="operator", password_hash="test-only"))
        session.add(AppUserFacilityRole(user_id="target", organization_id="org", facility_id="a", role="operator"))
    yield engine
    engine.dispose()


def context(role="admin", facility="a", user="actor"):
    return RequestContext(user, "org", facility, role, "Uploads")


def override(engine, permission, effect="deny", facility="a", org="org", user="actor"):
    with Session(engine) as session, session.begin():
        session.add(AppUserPermissionOverride(user_id=user, organization_id=org, facility_id=facility,
                    permission=permission, effect=effect, created_by="actor", updated_by="actor"))


@pytest.mark.parametrize("permission,roles", [
    ("inventory.receive", "dev admin buyer planner supervisor operator qa trial"),
    ("inventory.adjust", "dev admin supervisor operator qa"),
    ("audits.complete", "dev admin buyer supervisor operator qa trial"),
    ("cultivation.bulk_transition", "dev admin supervisor operator qa"),
    ("production.schedule", "dev admin planner supervisor"),
    ("qa.decide", "dev admin supervisor qa"),
    ("traceability.dispatch", "dev admin supervisor qa"),
    ("labels.advance_runs", "dev admin supervisor operator qa"),
    ("admin.manage_permissions", "dev admin"),
    ("ai.publish_knowledge", "dev admin supervisor qa"),
    *[(p, "dev admin buyer planner supervisor operator qa read_only trial user") for p in
      ("commercial.record_payment", "integrations.manage_metrc", "reports.export")],
])
def test_defaults_preserve_existing_endpoint_roles(permission, roles):
    assert {role for role, defaults in ROLE_DEFAULTS.items() if permission in defaults} == set(roles.split())


def test_wholesale_defaults_unchanged():
    wholesale = {p for p in PERMISSION_REGISTRY if p.startswith("wholesale.")}
    for role, defaults in ROLE_DEFAULTS.items():
        assert defaults & wholesale == (wholesale if role in {"dev", "admin", "buyer", "supervisor"} else {"wholesale.view"})


def test_override_scope_and_dev_exception(engine):
    override(engine, "inventory.adjust")
    override(engine, "production.schedule", "allow")
    assert not permission_snapshot(context(), engine)["effective"]["inventory.adjust"]
    assert permission_snapshot(context(facility="b"), engine)["effective"]["inventory.adjust"]
    assert permission_snapshot(replace(context(), organization_id="other"), engine)["effective"]["inventory.adjust"]
    assert permission_snapshot(context(user="target"), engine)["effective"]["inventory.adjust"]
    assert permission_snapshot(context("operator"), engine)["effective"]["production.schedule"]
    assert not permission_snapshot(context("operator", "b"), engine)["effective"]["production.schedule"]
    assert permission_snapshot(context("dev"), engine)["effective"]["inventory.adjust"]


# Execute real endpoint functions with denied permissions and unusable payloads.
# Any service/payload access before the authorization boundary would fail this test.
GATES = [
    ("inventory", "receive_inventory", "inventory.receive"),
    ("inventory", "receive_inventory_batch", "inventory.receive"),
    ("inventory", "adjust_inventory", "inventory.adjust"),
    ("audits", "complete_audit", "audits.complete"),
    ("cultivation_bulk", "bulk_transition_plants", "cultivation.bulk_transition"),
    ("production", "commit_schedule", "production.schedule"),
    ("production", "record_qa", "qa.decide"),
    ("extraction", "qa", "qa.decide"),
    *[("traceability_actions", name, "traceability.dispatch") for name in
      ("dispatch_action", "retry_traceability_exception", "resolve_traceability_exception")],
    *[("label_printing", name, "labels.advance_runs") for name in
      ("create_label_production_run", "assign_label_production_tag", "save_label_production_design",
       "record_label_production_print", "transition_label_production_run")],
    ("commercial", "record_payment", "commercial.record_payment"),
    ("integrations", "save_metrc", "integrations.manage_metrc"),
    ("integrations", "clear_metrc", "integrations.manage_metrc"),
    *[("executive_reports", name, "reports.export") for name in
      ("buyer_report_pdf", "white_label_report_pdf", "retail_pack_pdf", "production_pack_pdf",
       "cultivation_pack_pdf", "company_pack_pdf", "report_pdf")],
    ("ai_agents", "ingest_knowledge", "ai.publish_knowledge"),
]


@pytest.mark.parametrize("module,name,permission", GATES)
def test_high_risk_endpoint_denies_before_side_effects(engine, module, name, permission):
    override(engine, permission)
    endpoint = getattr(importlib.import_module(f"backend.app.routers.{module}"), name)
    args = {key: None for key in inspect.signature(endpoint).parameters}
    args.update(context=context(), engine=engine)
    with pytest.raises(HTTPException) as denied:
        result = endpoint(**args)
        if inspect.isawaitable(result):
            asyncio.run(result)
    assert denied.value.status_code == 403
    assert "permission" in denied.value.detail


def test_explicit_allow_keeps_legacy_role_gate(engine):
    from backend.app.routers.production import commit_schedule
    override(engine, "production.schedule", "allow")
    with pytest.raises(HTTPException, match="role cannot"):
        commit_schedule("missing", None, context("operator"), engine)


def test_admin_updates_are_scoped_audited_and_inherit_restores_defaults(engine):
    payload = UserPermissionUpdate(facility_id="a", overrides={"inventory.adjust": "deny"})
    result = update_user_permissions("target", payload, context(), engine)
    assert not result["effective"]["inventory.adjust"]
    payload.overrides = {"inventory.adjust": "inherit"}
    result = update_user_permissions("target", payload, context(), engine)
    assert result["effective"]["inventory.adjust"]
    with Session(engine) as session:
        assert len(session.scalars(select(AuditEvent).where(AuditEvent.action == "user_permissions_updated")).all()) == 2
    override(engine, "admin.manage_permissions", facility="a")
    with pytest.raises(HTTPException) as denied:
        update_user_permissions("target", payload, context(facility="b"), engine)
    assert denied.value.status_code == 403  # target facility, not caller's active facility


def test_readiness_is_honest_scoped_and_secret_free(engine):
    settings = Settings(_env_file=None, supabase_url="https://example.invalid", supabase_publishable_key="private-marker",
                        supabase_jwt_secret="jwt-marker", integration_encryption_key="encryption-marker")
    result = security_readiness(context(), engine, settings)
    controls = {row["key"]: row for row in result["controls"]}
    assert controls["supabase_auth"]["status"] == "configured"
    assert controls["integration_encryption"]["status"] == "configured"
    assert controls["permission_overrides"]["status"] == "available"
    for key in ("mfa", "sso", "scim"):
        assert controls[key]["status"] == "unsupported"
    assert "marker" not in str(result)
    override(engine, "inventory.adjust", facility="b")
    assert security_readiness(context(), engine, settings)["controls"][3]["status"] == "available"
    assert security_readiness(context(facility="b"), engine, settings)["controls"][3]["status"] == "observed"
    missing = Settings(_env_file=None, supabase_url="", supabase_publishable_key="", supabase_service_role_key="", integration_encryption_key="")
    assert security_readiness(context(), engine, missing)["controls"][0]["status"] == "not_configured"
    with pytest.raises(HTTPException):
        security_readiness(context("operator"), engine, settings)


def test_admin_registry_and_ui_contract():
    rows = permission_registry(context())
    assert len({row["group"] for row in rows}) == 13
    assert all(row["description"] and row["label"] for row in rows)
    ui = Path("frontend/src/components/UserPermissionManager.tsx").read_text(encoding="utf-8")
    assert "groups.map(group" in ui and "permission.group===group" in ui
    assert "Allow does not bypass" in ui and "permission.coverage" in ui
    readiness = Path("frontend/src/components/SecurityReadiness.tsx").read_text(encoding="utf-8")
    assert "/api/v1/admin/security-readiness" in readiness and "Evidence and limits" in readiness


def test_http_gate_blocks_mutation_and_preserves_default_access(engine, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.auth import get_request_context, get_production_context
    from backend.app.database import get_engine
    from backend.app.routers import production

    calls = []

    class Service:
        def commit(self, **kwargs):
            calls.append(kwargs)
            return {"saved": True}

    monkeypatch.setattr(production, "_schedule_service", lambda engine: Service())
    app = FastAPI()
    app.include_router(production.router)
    app.dependency_overrides[get_request_context] = lambda: context("planner")
    app.dependency_overrides[get_production_context] = lambda: context("planner")
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        payload = {"scheduled_start_at": "2026-09-25T12:00:00", "scheduled_end_at": "2026-09-25T13:00:00", "preview_key": "test-preview"}
        response = client.post("/production/orders/order/schedule", json=payload)
        assert response.status_code == 200, response.text
        assert len(calls) == 1 and calls[0]["facility_id"] == "a"
        override(engine, "production.schedule")
        response = client.post("/production/orders/order/schedule", json=payload)
        assert response.status_code == 403
        assert len(calls) == 1


def test_admin_rejects_unassigned_facility_and_cross_org(engine):
    payload = UserPermissionUpdate(facility_id="b", overrides={"inventory.adjust": "allow"})
    with pytest.raises(HTTPException) as missing_assignment:
        update_user_permissions("target", payload, context(), engine)
    assert missing_assignment.value.status_code == 422
    with pytest.raises(HTTPException) as cross_org:
        update_user_permissions("target", payload, replace(context(), organization_id="other"), engine)
    assert cross_org.value.status_code == 403


def test_readiness_unavailable_storage_is_not_reported_ready():
    engine = create_engine("sqlite://")
    result = security_readiness(context(), engine, Settings(_env_file=None))
    controls = {row["key"]: row for row in result["controls"]}
    assert controls["permission_overrides"]["status"] == "unavailable"
    assert controls["audit_logging"]["status"] == "unavailable"
    engine.dispose()
