from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.config import Settings
from backend.app.routers.adoption import (ActiveInput, AnnotationInput, SubscriptionInput, admin, annotate,
    create_subscription, history, set_active, subscriptions)
from backend.app.services import scheduled_reports as reports
from backend.app.services.adoption_models import ReadinessAnnotation, ReportDelivery, ReportSubscription
from backend.app.services.implementation_readiness import readiness
from modules.coman.models import Base, Facility, Organization, InventoryAudit, InventoryLot, InventoryTransaction, Product, AuditEvent
from modules.integrations.models import IntegrationConfiguration, IntegrationSyncState

NOW = datetime(2026, 1, 31, 12, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'adoption.db'}")
    names = {"coman_organizations", "coman_facilities", "coman_products", "coman_inventory_lots",
             "coman_inventory_transactions", "coman_production_actuals", "app_users", "app_user_facility_roles",
             "coman_audit_events", "commerce_storefronts", "integration_configurations", "integration_sync_states",
             "facility_readiness_annotations", "report_subscriptions", "report_deliveries", "product_master_profiles",
             "inventory_audits", "commercial_orders", "app_user_permission_overrides", "doobie_work_items", "doobie_work_templates"}
    Base.metadata.create_all(engine, tables=[table for name, table in Base.metadata.tables.items() if name in names])
    with Session(engine) as session:
        session.add(Organization(id="org", name="Org", slug="org"))
        session.flush()
        session.add_all([Facility(id=key, organization_id="org", name=key, code=key) for key in ("one", "two")])
        session.commit()
    yield engine, RequestContext("admin", "org", "one", "admin", capabilities=frozenset({"production"}))
    engine.dispose()


def create(engine, context):
    row = create_subscription(SubscriptionInput(report_type="production", recipients=["ops@example.com"], cadence="monthly"), context, engine)
    with Session(engine) as session:
        subscription = session.get(ReportSubscription, row["id"])
        subscription.next_run = NOW
        session.commit()
    return row["id"]


def test_schedule_utc_calendar_edges():
    assert reports.next_occurrence(NOW, "monthly") == datetime(2026, 2, 28, 12, tzinfo=timezone.utc)
    assert reports.next_occurrence(datetime(2024, 1, 31), "monthly").day == 29
    assert reports.next_occurrence(datetime(2026, 12, 31), "monthly").year == 2027
    assert (reports.next_occurrence(NOW, "weekly") - NOW).days == 7
    assert (reports.next_occurrence(NOW, "daily") - NOW).days == 1


def test_readiness_query_count_is_bounded(setup):
    from sqlalchemy import event
    engine, context = setup
    with Session(engine) as session:
        session.add_all(Product(organization_id="org", sku=f"sku-{index}", name="Catalog product", item_type="cannabis") for index in range(250))
        session.commit()
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert readiness(engine, context)["items"]
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) <= 12  # Two batch user projections, never per-item queries.


def test_readiness_evidence_is_facility_scoped_and_credentials_not_verification(setup):
    engine, context = setup
    with Session(engine) as session:
        session.add(Product(id="p", organization_id="org", sku="p", name="Product", item_type="cannabis"))
        session.flush()
        session.add(InventoryLot(id="lot", organization_id="org", facility_id="two", product_id="p", lot_code="lot"))
        session.flush()
        session.add(InventoryTransaction(organization_id="org", facility_id="two", lot_id="lot", transaction_type="receive", quantity_delta=1, unit="g", actor="admin"))
        session.add(IntegrationConfiguration(organization_id="org", facility_id="one", scope_type="facility", scope_key="one", provider="metrc", status="configured", encrypted_secret="not-a-real-key", updated_by="admin"))
        session.commit()
    items = {item["key"]: item for item in readiness(engine, context)["items"]}
    assert items["facility"]["status"] == "complete"
    assert items["inventory"]["status"] == "incomplete"
    assert items["catalog"]["status"] == "complete"  # Catalog is organization-owned.
    assert items["traceability"]["status"] == "needs_review"
    other = RequestContext("admin", "org", "two", "admin")
    assert next(item for item in readiness(engine, other)["items"] if item["key"] == "inventory")["status"] == "complete"
    with Session(engine) as session:
        config = session.scalar(select(IntegrationConfiguration))
        config.status, config.last_validated_at = "connected", NOW
        session.add(IntegrationSyncState(organization_id="org", facility_id="one", provider="metrc", resource="packages", environment="production", status="succeeded", last_success_at=NOW, updated_by="admin"))
        session.commit()
    assert next(item for item in readiness(engine, context)["items"] if item["key"] == "traceability")["status"] == "complete"


def test_manual_notes_and_automatic_override_guard(setup):
    engine, context = setup
    annotate("permissions", AnnotationInput(notes="Reviewed assigned roles", manual_status="complete"), context, engine)
    assert next(item for item in readiness(engine, context)["items"] if item["key"] == "permissions")["status"] == "complete"
    with pytest.raises(HTTPException) as error:
        annotate("inventory", AnnotationInput(notes="Override", manual_status="complete"), context, engine)
    assert error.value.status_code == 422
    with pytest.raises(HTTPException):
        annotate("permissions", AnnotationInput(manual_status="complete"), context, engine)
    with Session(engine) as session:
        assert session.scalar(select(ReadinessAnnotation)).owner_user_id is None
        assert session.scalar(select(AuditEvent)) is not None


def test_completed_inventory_workflow_and_not_applicable_storefront(setup):
    engine, context = setup
    with Session(engine) as session:
        facility = session.get(Facility, "one")
        facility.production_enabled = False
        facility.commercial_enabled = False
        session.add(InventoryAudit(organization_id="org", facility_id="one", audit_number="opening",
            status="completed", completed_at=NOW, created_by="admin"))
        session.commit()
    items = {item["key"]: item for item in readiness(engine, context)["items"]}
    assert items["first_workflow"]["status"] == "complete"
    assert items["storefront"]["status"] == "not_applicable"


def test_admin_and_recipient_validation():
    with pytest.raises(HTTPException) as error:
        admin(RequestContext("reader", "org", "one", "read_only"))
    assert error.value.status_code == 403
    for recipient in ("bad", "person@example.com\r\nBcc: other@example.com"):
        with pytest.raises(ValueError):
            SubscriptionInput(report_type="production", recipients=[recipient], cadence="daily")


def test_mail_unavailable_is_durable_and_due_idempotent(setup, monkeypatch):
    engine, context = setup
    key = create(engine, context)
    monkeypatch.setattr(reports.spacemail, "resolve_spacemail_settings", lambda *_: Mock(spacemail_is_configured=False))
    first = reports.process_due(engine, Settings(), context, NOW)
    assert first["items"][0]["status"] == "deferred"
    assert reports.process_due(engine, Settings(), context, NOW)["items"] == []
    assert len(history(context, engine)["items"]) == 1
    assert subscriptions(context, engine)["items"][0]["last_run"] is not None
    other = RequestContext("admin", "org", "two", "admin")
    assert subscriptions(other, engine)["items"] == history(other, engine)["items"] == []
    with pytest.raises(HTTPException) as error:
        reports.deliver(engine, Settings(), other, key, request_key="other")
    assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        set_active(key, ActiveInput(active=False), other, engine)


def test_smtp_pdf_delivery_and_manual_idempotency(setup, monkeypatch):
    engine, context = setup
    key = create(engine, context)
    mail = Mock(spacemail_is_configured=True, spacemail_from_email="reports@example.com")
    monkeypatch.setattr(reports.spacemail, "resolve_spacemail_settings", lambda *_: mail)
    monkeypatch.setattr(reports.spacemail, "test_spacemail_connection", lambda *_: {"ok": True})
    monkeypatch.setattr(reports, "generate_report", lambda *_: b"%PDF" + b"x" * 600)
    smtp = Mock()
    smtp.send_message.return_value = {}
    connection = Mock()
    connection.__enter__ = Mock(return_value=smtp)
    connection.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(reports.spacemail, "_smtp_login", lambda *_: connection)
    run = reports.deliver(engine, Settings(), context, key, request_key="same", now=NOW)
    assert run["status"] == "sent"
    assert reports.deliver(engine, Settings(), context, key, request_key="same", now=NOW)["id"] == run["id"]
    assert smtp.send_message.call_count == 1
    message = smtp.send_message.call_args.args[0]
    assert next(message.iter_attachments()).get_content_type() == "application/pdf"
    assert smtp.send_message.call_args.kwargs["to_addrs"] == ["ops@example.com"]
    smtp.send_message.side_effect = TimeoutError("private details")
    uncertain = reports.deliver(engine, Settings(), context, key, request_key="uncertain", now=NOW)
    assert uncertain["status"] == "needs_review"
    assert "private" not in uncertain["detail"]
    reports.deliver(engine, Settings(), context, key, request_key="uncertain", now=NOW)
    assert smtp.send_message.call_count == 2


def test_paused_subscription_is_not_due(setup, monkeypatch):
    engine, context = setup
    key = create(engine, context)
    set_active(key, ActiveInput(active=False), context, engine)
    sender = Mock()
    monkeypatch.setattr(reports.spacemail, "resolve_spacemail_settings", sender)
    assert reports.process_due(engine, Settings(), context, NOW)["items"] == []
    sender.assert_not_called()


def test_concurrent_due_workers_reserve_only_one_attempt(setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    engine, context = setup
    create(engine, context)
    resolver = Mock(return_value=Mock(spacemail_is_configured=False))
    monkeypatch.setattr(reports.spacemail, "resolve_spacemail_settings", resolver)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: reports.process_due(engine, Settings(), context, NOW), range(2)))
    assert sum(len(result["items"]) for result in results) <= 2  # A concurrent caller may read the same receipt.
    assert resolver.call_count == 1
    with Session(engine) as session:
        assert len(list(session.scalars(select(ReportDelivery)))) == 1


def test_failed_validation_and_revoked_capability_are_visible(setup, monkeypatch):
    engine, context = setup
    key = create(engine, context)
    monkeypatch.setattr(reports.spacemail, "resolve_spacemail_settings", lambda *_: Mock(spacemail_is_configured=True))
    monkeypatch.setattr(reports.spacemail, "test_spacemail_connection", lambda *_: {"ok": False})
    generator = Mock()
    monkeypatch.setattr(reports, "generate_report", generator)
    assert reports.deliver(engine, Settings(), context, key, request_key="validation")["status"] == "deferred"
    generator.assert_not_called()
    restricted = RequestContext("admin", "org", "one", "admin", capabilities=frozenset({"retail"}))
    assert reports.process_due(engine, Settings(), restricted, NOW)["items"][0]["status"] == "failed"


def test_api_rejects_non_admin_and_foreign_organization(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.auth import get_request_context
    from backend.app.database import get_engine
    from backend.app.routers.adoption import router
    engine, context = setup
    key = create(engine, context)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_request_context] = lambda: RequestContext("reader", "org", "one", "read_only")
    with TestClient(app) as client:
        assert client.get("/report-subscriptions").status_code == 403
        assert client.post("/report-subscriptions/process-due").status_code == 403
        assert client.post("/implementation-readiness/permissions", json={"notes": "review"}).status_code == 403
        assert client.post("/implementation-readiness/inventory/work").status_code == 403
        app.dependency_overrides[get_request_context] = lambda: RequestContext("admin", "foreign", "one", "admin")
        assert client.get("/report-subscriptions").json()["items"] == []
        assert client.post(f"/report-subscriptions/{key}/active", json={"active": False}).status_code == 404


def test_migration_matches_models_and_preserves_evidence(tmp_path):
    import importlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    migration = importlib.import_module("migrations.versions.0083_onboarding_reporting")
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            for model in (ReadinessAnnotation, ReportSubscription, ReportDelivery):
                actual = {column["name"] for column in inspect(connection).get_columns(model.__tablename__)}
                assert actual == set(model.__table__.columns.keys())
            connection.execute(ReadinessAnnotation.__table__.insert().values(id="test", organization_id="org", facility_id="facility", item_key="permissions", updated_by="admin"))
            with pytest.raises(RuntimeError, match="Preserve evidence"):
                migration.downgrade()
    engine.dispose()


def test_canonical_owner_eligibility_and_projection(setup):
    from modules.coman.models import AppUser, AppUserFacilityRole
    engine, context = setup
    with Session(engine) as session, session.begin():
        session.add(Organization(id="foreign", name="Foreign", slug="foreign"))
        session.flush()
        for user, org, role, active in [("admin", "org", "admin", True), ("dev", "org", "dev", True),
                ("eligible", "org", "operator", True), ("elsewhere", "org", "operator", True),
                ("inactive", "org", "operator", False), ("foreign", "foreign", "admin", True)]:
            session.add(AppUser(id=user, organization_id=org, username=user, normalized_username=user,
                display_name="Same display name", role=role, active=active, password_hash="test-only"))
        session.flush()
        for user, facility in [("eligible", "one"), ("inactive", "one"), ("elsewhere", "two")]:
            session.add(AppUserFacilityRole(user_id=user, organization_id="org", facility_id=facility, role="operator"))
    for user in ["admin", "dev", "eligible"]:
        annotate("inventory", AnnotationInput(owner_user_id=user), context, engine)
        result = readiness(engine, context)
        item = next(i for i in result["items"] if i["key"] == "inventory")
        assert item["owner_user_id"] == user and item["owner_name"] == "Same display name"
        assert {u["id"] for u in result["owner_options"]} == {"admin", "dev", "eligible"}
    for user in ["elsewhere", "inactive", "foreign", "missing", "Same display name"]:
        with pytest.raises(HTTPException) as error:
            annotate("inventory", AnnotationInput(owner_user_id=user), context, engine)
        assert error.value.status_code == 422
    with pytest.raises(ValueError):
        AnnotationInput(owner="Same display name")
    annotate("inventory", AnnotationInput(owner_user_id=None), context, engine)
    assert next(i for i in readiness(engine, context)["items"] if i["key"] == "inventory")["owner_user_id"] is None


def test_explicit_work_link_is_transactional_and_work_remains_authoritative(setup, monkeypatch):
    from backend.app.routers import adoption
    from backend.app.services.work import WorkService
    from backend.app.schemas.work import WorkUpdate
    from modules.coman.models import WorkItem
    engine, context = setup
    readiness(engine, context)
    with Session(engine) as session:
        assert session.scalar(select(WorkItem)) is None
    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(adoption, "audit", fail)
        with pytest.raises(RuntimeError):
            adoption.create_readiness_work("inventory", context, engine)
    with Session(engine) as session:
        assert session.scalar(select(WorkItem)) is None
        assert session.scalar(select(ReadinessAnnotation)) is None
    result = adoption.create_readiness_work("inventory", context, engine)
    assert adoption.create_readiness_work("inventory", context, engine) == result
    work = WorkService(engine, context).get(result["work_item_id"])
    assert work["route"] == "/settings/implementation#inventory"
    assert work["entity_type"] == "implementation_readiness"
    WorkService(engine, context).update(work["id"], WorkUpdate(version=1, status="completed", priority="high"))
    annotate("inventory", AnnotationInput(notes="Review opening balances", target_date=NOW.date()), context, engine)
    item = next(i for i in readiness(engine, context)["items"] if i["key"] == "inventory")
    assert item["status"] == "incomplete" and item["work_item_id"] == work["id"]
    assert WorkService(engine, context).get(work["id"])["due_at"] is None
    assert not {"priority", "assignee_id", "status", "due_at"} & set(ReadinessAnnotation.__table__.columns.keys())


def test_report_export_denial_blocks_creation_and_records_failed_delivery(setup, monkeypatch):
    from modules.coman.permissions import AppUserPermissionOverride
    engine, context = setup
    key = create(engine, context)
    with Session(engine) as session, session.begin():
        session.add(AppUserPermissionOverride(user_id=context.user_id, organization_id="org", facility_id="one",
            permission="reports.export", effect="deny", created_by=context.user_id, updated_by=context.user_id))
    with pytest.raises(HTTPException) as error:
        create(engine, context)
    assert error.value.status_code == 403
    sender = Mock()
    monkeypatch.setattr(reports.spacemail, "resolve_spacemail_settings", sender)
    assert reports.deliver(engine, Settings(), context, key, request_key="denied")["status"] == "failed"
    sender.assert_not_called()


def test_migration_chain_and_postgres_browser_restrictions():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from io import StringIO
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_heads() == ["0084_wholesale_logistics"]
    revision = scripts.get_revision("0083_onboarding_reporting")
    assert revision.down_revision == "0082_white_label_execution"
    buffer = StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})):
        revision.module.upgrade()
    sql = buffer.getvalue()
    assert "REFERENCES app_users (id) ON DELETE SET NULL" in sql
    assert "REFERENCES doobie_work_items (id) ON DELETE SET NULL" in sql
    for table in revision.module.TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC" in sql
    assert "ARRAY['anon','authenticated']" in sql
