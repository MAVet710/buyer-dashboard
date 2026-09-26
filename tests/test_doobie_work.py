import importlib
import json
from io import StringIO
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.permissions import AppUserPermissionOverride
from backend.app.auth import RequestContext, get_request_context
from backend.app.database import get_engine
from backend.app.routers.work import router
from backend.app.schemas.work import TemplateCreate, TemplateUpdate, WorkCreate, WorkUpdate
from backend.app.services.work import WorkService, occurrence
from modules.coman.models import AppUser, AppUserFacilityRole, AuditEvent, Base, Facility, Organization, WorkItem, WorkTemplate

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    tables = [AppUserPermissionOverride, Organization, Facility, AppUser, AppUserFacilityRole, AuditEvent, WorkTemplate, WorkItem]
    Base.metadata.create_all(engine, tables=[m.__table__ for m in tables])
    with Session(engine) as session, session.begin():
        session.add_all([Organization(id="org", name="Work", slug="work"), Organization(id="other", name="Other", slug="other")])
        session.flush()
        session.add_all([Facility(id="f1", organization_id="org", name="One", code="ONE"),
                         Facility(id="f2", organization_id="org", name="Two", code="TWO"),
                         Facility(id="f3", organization_id="other", name="Other", code="OTHER")])
        for user, org, role, active in [("u1", "org", "operator", True), ("u2", "org", "qa", True),
                ("u3", "other", "admin", True), ("inactive", "org", "operator", False),
                ("reader", "org", "read_only", True), ("admin", "org", "admin", True), ("otherfacility", "org", "operator", True)]:
            session.add(AppUser(id=user, organization_id=org, username=user, normalized_username=user,
                                role=role, active=active, password_hash="test-only"))
        session.flush()
        for user, facility, role in [("u1", "f1", "operator"), ("u2", "f1", "qa"),
                ("inactive", "f1", "operator"), ("reader", "f1", "read_only"), ("otherfacility", "f2", "operator")]:
            session.add(AppUserFacilityRole(user_id=user, organization_id="org", facility_id=facility, role=role))
    context = RequestContext("u1", "org", "f1", "operator")
    yield engine, context, WorkService(engine, context)
    engine.dispose()


def test_assignment_lifecycle_completion_reopen_and_audit(setup):
    engine, _, service = setup
    row = service.create(WorkCreate(title="Cycle count", assignee_id="u1", due_at=NOW, workspace="Inventory", route="/inventory"))
    row = service.update(row["id"], WorkUpdate(version=1, status="in_progress", assignee_id="u2"))
    row = service.update(row["id"], WorkUpdate(version=2, status="blocked", blocked_reason="Waiting for count", notes="Shelf A"))
    row = service.update(row["id"], WorkUpdate(version=3, status="completed", evidence="Count sheet 42"))
    assert row["completed_by"] == "u1" and row["completed_at"] and not row["blocked_reason"]
    row = service.update(row["id"], WorkUpdate(version=4, status="open", assignee_id=None, due_at=None))
    assert row["completed_by"] is None and row["completed_at"] is None and row["assignee_id"] is None and row["due_at"] is None
    assert row["evidence"] == "Count sheet 42"
    with Session(engine) as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at)).all()
        assert len(events) == 5
        last = json.loads(events[-1].changes_json)["_event"]
        assert last["before"]["status"] == "completed" and last["after"]["status"] == "open"
        assert all(e.facility_id == "f1" and e.actor == "u1" for e in events)


@pytest.mark.parametrize("organization,facility", [("org", "f2"), ("other", "f3")])
def test_isolation_for_every_read_write_and_generation(setup, organization, facility):
    engine, context, service = setup
    row = service.create(WorkCreate(title="Private", assignee_id="u1"))
    template = service.create(TemplateCreate(title="Private recurring", frequency="daily", starts_at=NOW), template=True)
    other = WorkService(engine, replace(context, organization_id=organization, facility_id=facility))
    assert other.list()["items"] == [] and other.templates()["items"] == []
    assert other.generate(NOW)["generated"] == 0
    for operation in [lambda: other.get(row["id"]), lambda: other.update(row["id"], WorkUpdate(version=1, status="completed")),
                      lambda: other.update(template["id"], TemplateUpdate(version=1, active=False), template=True)]:
        with pytest.raises(HTTPException) as error:
            operation()
        assert error.value.status_code == 404


@pytest.mark.parametrize("assignee", ["u3", "inactive", "reader", "otherfacility", "missing"])
def test_assignment_rejects_ineligible_users_without_partial_mutation(setup, assignee):
    engine, _, service = setup
    with pytest.raises(HTTPException):
        service.create(WorkCreate(title="Invalid", assignee_id=assignee))
    row = service.create(WorkCreate(title="Valid"))
    with pytest.raises(HTTPException):
        service.update(row["id"], WorkUpdate(version=1, assignee_id=assignee))
    assert service.get(row["id"])["version"] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_assignee_list_uses_existing_facility_roles(setup):
    _, _, service = setup
    assert {u["id"] for u in service.assignees()["items"]} == {"u1", "u2", "admin"}


@pytest.mark.parametrize("role", ["read_only", "user", "trial", "unknown"])
def test_readers_cannot_mutate_even_through_service(setup, role):
    engine, context, writer = setup
    row = writer.create(WorkCreate(title="Read me"))
    template = writer.create(TemplateCreate(title="Recurring", frequency="daily", starts_at=NOW), template=True)
    service = WorkService(engine, replace(context, role=role))
    assert service.get(row["id"])["title"] == "Read me"
    for operation in [lambda: service.create(WorkCreate(title="No")), lambda: service.generate(NOW),
            lambda: service.update(row["id"], WorkUpdate(version=1, status="completed")),
            lambda: service.create(TemplateCreate(title="No", frequency="daily", starts_at=NOW), template=True),
            lambda: service.update(template["id"], TemplateUpdate(version=1, active=False), template=True)]:
        with pytest.raises(HTTPException) as error:
            operation()
        assert error.value.status_code == 403


@pytest.mark.parametrize("role", ["dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"])
def test_operational_roles_can_manage_work(setup, role):
    engine, context, _ = setup
    service = WorkService(engine, replace(context, role=role))
    row = service.create(WorkCreate(title=role, assignee_id="u2"))
    assert service.update(row["id"], WorkUpdate(version=1, status="completed"))["completed_by"] == "u1"


def test_stale_versions_blocked_reason_and_atomic_audit(setup, monkeypatch):
    engine, _, service = setup
    row = service.create(WorkCreate(title="Versioned"))
    with pytest.raises(HTTPException) as error:
        service.update(row["id"], WorkUpdate(version=2, status="completed"))
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        service.update(row["id"], WorkUpdate(version=1, status="blocked"))
    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr("backend.app.services.work.audit", fail)
    with pytest.raises(RuntimeError):
        service.update(row["id"], WorkUpdate(version=1, status="completed"))
    assert service.get(row["id"])["version"] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize("frequency,days,count", [("daily", 3, 4), ("weekly", 21, 4), ("monthly", 100, 4)])
def test_recurrence_idempotent_and_end_bounded(setup, frequency, days, count):
    _, _, service = setup
    template = service.create(TemplateCreate(title="Routine", frequency=frequency, starts_at=NOW,
                   ends_at=NOW + timedelta(days=days), assignee_id="u1"), template=True)
    result = service.generate(NOW + timedelta(days=days + 7))
    assert result["generated"] == count
    assert service.generate(NOW + timedelta(days=days + 7))["generated"] == 0
    rows = service.list()["items"]
    assert len({r["occurrence_at"] for r in rows}) == count
    assert all(r["template_id"] == template["id"] and r["assignee_id"] == "u1" for r in rows)


def test_month_end_leap_year_and_timezone_anchor():
    anchor = datetime(2024, 1, 31, 8, tzinfo=timezone.utc)
    assert occurrence(anchor, "monthly", 1).day == 29
    assert occurrence(anchor, "monthly", 2).day == 31
    assert occurrence(anchor, "monthly", 13).day == 28
    assert occurrence(anchor, "weekly", 1) == anchor + timedelta(days=7)


def test_template_assignment_can_be_repaired_after_deactivation(setup):
    engine, _, service = setup
    template = service.create(TemplateCreate(title="Daily", frequency="daily", starts_at=NOW, assignee_id="u2"), template=True)
    with Session(engine) as session, session.begin():
        session.get(AppUser, "u2").active = False
    with pytest.raises(HTTPException):
        service.generate(NOW)
    assert service.list()["items"] == []
    service.update(template["id"], TemplateUpdate(version=1, assignee_id="u1"), template=True)
    assert service.generate(NOW)["generated"] == 1
    assert service.list()["items"][0]["assignee_id"] == "u1"


def test_home_inbox_keeps_existing_shape_and_scopes_assigned_work(setup):
    engine, context, service = setup
    Base.metadata.create_all(engine)
    from backend.app.routers.home import operations_inbox
    row = service.create(WorkCreate(title="Assigned urgent", priority="high", assignee_id="u1"))
    service.create(WorkCreate(title="Someone else", priority="critical", assignee_id="u2"))
    service.create(WorkCreate(title="Not urgent", assignee_id="u1"))
    service.create(WorkCreate(title="Overdue", assignee_id="u1", due_at=NOW - timedelta(days=1000)))
    result = operations_inbox(context, engine)
    items = [i for i in result["items"] if i["area"] == "Work"]
    assert {i["title"] for i in items} == {"Assigned urgent", "Overdue"}
    assert next(i for i in items if i["title"] == "Assigned urgent")["route"] == f"/work?item={row['id']}"
    assert result["summary"]["high"] >= 2


def test_generation_batch_catchup_pause_resume_and_recovery(setup, monkeypatch):
    _, _, service = setup
    template = service.create(TemplateCreate(title="Daily", frequency="daily", starts_at=NOW), template=True)
    assert service.generate(NOW + timedelta(days=120))["generated"] == 100
    t = service.templates()["items"][0]
    t = service.update(t["id"], TemplateUpdate(version=t["version"], active=False), template=True)
    assert service.generate(NOW + timedelta(days=120))["generated"] == 0
    service.update(t["id"], TemplateUpdate(version=t["version"], active=True), template=True)
    from backend.app.services import work
    original = work.audit
    def fail(*args, **kwargs):
        raise RuntimeError("interrupted")
    monkeypatch.setattr(work, "audit", fail)
    with pytest.raises(RuntimeError):
        service.generate(NOW + timedelta(days=120))
    monkeypatch.setattr(work, "audit", original)
    assert service.generate(NOW + timedelta(days=120))["generated"] == 21
    assert service.generate(NOW + timedelta(days=120))["generated"] == 0
    assert service.templates()["items"][0]["id"] == template["id"]


def test_list_filters_pagination_and_constant_query_count(setup, monkeypatch):
    engine, _, service = setup
    monkeypatch.setattr("backend.app.services.work.utc_now", lambda: NOW)
    for i in range(55):
        service.create(WorkCreate(title=f"Task {i}", assignee_id="u1", due_at=NOW - timedelta(days=1),
                                 description="large", notes="large", evidence="large", workspace="Inventory"))
    due = service.create(WorkCreate(title="Tomorrow", due_at=NOW + timedelta(hours=1), assignee_id="u2"))
    count = []
    @event.listens_for(engine, "before_cursor_execute")
    def queries(*args):
        count.append(1)
    result = service.list(view="mine")
    assert len(count) == 1 and result["has_more"] and len(result["items"]) == 50
    assert not {"description", "notes", "evidence"} & result["items"][0].keys()
    assert len(service.list(view="overdue", offset=50)["items"]) == 5
    assert service.list(view="due")["items"][0]["id"] == due["id"]
    assert service.list(assignee_id="u2", workspace="Inventory")["items"] == []


@pytest.mark.parametrize("route", ["https://evil.test", "//evil.test", "/%2Fevil.test", "/inventory/../api", "/inventory\\evil", "/api/v1/admin"])
def test_route_injection_rejected(route):
    with pytest.raises(ValidationError):
        WorkCreate(title="Unsafe link", route=route)


def test_schema_rejects_naive_time_orphan_reference_and_null_status():
    for values in [{"title": " "}, {"title": "Task", "due_at": "2026-09-25T08:00:00"}, {"title": "Task", "entity_id": "orphan"}]:
        with pytest.raises(ValidationError):
            WorkCreate(**values)
    with pytest.raises(ValidationError):
        WorkUpdate(version=1, status=None)


def test_api_permissions_completion_reopen_and_validation(setup):
    engine, context, _ = setup
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_request_context] = lambda: context
    with TestClient(app) as client:
        row = client.post("/api/v1/work", json={"title": "API work"}).json()
        assert client.post(f"/api/v1/work/{row['id']}/complete", json={"version": 1}).json()["status"] == "completed"
        assert client.post(f"/api/v1/work/{row['id']}/reopen", json={"version": 2}).json()["status"] == "open"
        assert client.get("/api/v1/work?limit=1000").status_code == 422
        assert client.get("/api/v1/work?status=invalid").status_code == 422
        app.dependency_overrides[get_request_context] = lambda: replace(context, role="read_only")
        assert client.patch(f"/api/v1/work/{row['id']}", json={"version": 3, "assignee_id": "u2"}).status_code == 403


def test_migration_matches_models_and_refuses_data_loss(setup):
    engine, _, service = setup
    migration = importlib.import_module("migrations.versions.0080_doobie_work")
    WorkItem.__table__.drop(engine)
    WorkTemplate.__table__.drop(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    for model in (WorkItem, WorkTemplate):
        columns = {c["name"]: c for c in inspect(engine).get_columns(model.__tablename__)}
        assert set(columns) == {c.name for c in model.__table__.columns}
        for col in model.__table__.columns:
            assert columns[col.name]["nullable"] == col.nullable
    service.create(WorkCreate(title="Retain this"))
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        with pytest.raises(RuntimeError, match="Work records exist"):
            migration.downgrade()
    assert "doobie_work_templates" in inspect(engine).get_table_names()


def test_postgresql_migration_ddl_protects_browser_access():
    migration = importlib.import_module("migrations.versions.0080_doobie_work")
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration.upgrade()
    sql = output.getvalue()
    assert "uq_work_occurrence UNIQUE (template_id, occurrence_at)" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql and "['anon','authenticated']" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" not in sql
    assert migration.down_revision == "0079_security_observation"


def test_work_creation_override_preserves_role_gate(setup):
    engine, context, service = setup
    template = service.create(TemplateCreate(title="Recurring", frequency="daily", starts_at=NOW), template=True)
    with Session(engine) as session, session.begin():
        override = AppUserPermissionOverride(user_id=context.user_id, organization_id=context.organization_id,
            facility_id=context.facility_id, permission="work.create", effect="deny", created_by="test", updated_by="test")
        session.add(override)
    for operation in [lambda: service.create(WorkCreate(title="Denied")), lambda: service.generate(NOW)]:
        with pytest.raises(HTTPException) as error:
            operation()
        assert error.value.status_code == 403
    with Session(engine) as session, session.begin():
        session.scalar(select(AppUserPermissionOverride)).effect = "allow"
    assert service.create(WorkCreate(title="Allowed"))["id"]
    reader = WorkService(engine, replace(context, role="read_only"))
    with pytest.raises(HTTPException) as error:
        reader.create(WorkCreate(title="Role still required"))
    assert error.value.status_code == 403
    assert template["id"]
