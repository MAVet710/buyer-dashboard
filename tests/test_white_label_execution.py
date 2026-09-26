import copy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext, get_request_context
from backend.app.database import get_engine
from backend.app.routers.white_label import PlanSave, router
from modules.coman.models import (Base, Facility, InventoryLot, InventoryTransaction,
    MaterialReservation, Organization, Product, ProductionOrder, AuditEvent)
from modules.inventory_quality.models import LotQualityEvidence
from modules.repack.execution import WhiteLabelService
from modules.package_studio.service import PackageStudioInputPlan, PackageStudioOutputPlan, PackageStudioPlan, PackageStudioService


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(id="org", name="Repack", slug="repack")
        session.add(org)
        session.flush()
        session.add_all([Facility(id="facility", organization_id="org", name="Production", code="P", production_enabled=True),
                         Facility(id="other", organization_id="org", name="Other", code="O", production_enabled=True),
                         Product(id="product", organization_id="org", sku="BULK", name="Bulk flower", item_type="cannabis", base_unit="g")])
        session.flush()
        session.add(InventoryLot(id="lot", organization_id="org", facility_id="facility", product_id="product", lot_code="BULK-1", status="available"))
        session.flush()
        session.add_all([InventoryTransaction(organization_id="org", facility_id="facility", lot_id="lot", transaction_type="receipt", quantity_delta=1000, unit="g", actor="seed"),
            LotQualityEvidence(lot_id="lot", organization_id="org", facility_id="facility", lab_testing_state="passed", coa_reference="coa-reviewed", actor="qa")])
        session.commit()
    payload = PlanSave.model_validate(dict(name="Repack plan", source_lot_id="lot", scenario=dict(
        form=dict(bulk_weight_value=100, bulk_weight_unit="g", bulk_total_cost_usd=50, coa_link="operator note"),
        plan=[dict(enabled=True, package_size_g=3.5, allocation_pct=100, target_retail_price_per_unit=20)]))).model_dump()
    return engine, WhiteLabelService(engine), payload


def save(service, payload):
    return service.save("org", "facility", "planner", payload)


def test_durable_reload_idempotent_approval_and_no_inventory_claim(setup):
    engine, service, payload = setup
    draft = save(service, payload)
    reloaded = WhiteLabelService(engine).get("org", "facility", draft["id"])
    assert reloaded["scenario"] == payload["scenario"]
    assert reloaded["source"]["coa_reference"] == "coa-reviewed"
    assert reloaded["economics"]["total_units"] == 28
    assert reloaded["status"] == "draft"
    approved = service.approve("org", "facility", "planner", draft["id"], draft["revision"])
    retried = service.approve("org", "facility", "planner", draft["id"], draft["revision"])
    assert approved == retried
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProductionOrder)) == 1
        assert session.scalar(select(func.count()).select_from(MaterialReservation)) == 0
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
        assert session.scalar(select(func.sum(InventoryTransaction.quantity_delta))) == 1000
        order = session.get(ProductionOrder, approved["production_order_id"])
        assert order.status == "draft"
        notes = json.loads(order.notes)
        assert notes["white_label_plan_id"] == draft["id"]
        assert notes["source"]["lot_id"] == "lot"
        assert notes["expected_outputs"][0]["units"] == 28
        events = list(session.scalars(select(AuditEvent)))
        assert {json.loads(event.changes_json)["_event"]["correlation_id"] for event in events} == {draft["id"]}


@pytest.mark.parametrize("org,facility", [("outside", "facility"), ("org", "other")])
def test_scope_cannot_read_save_or_approve_another_facility(setup, org, facility):
    _, service, payload = setup
    draft = save(service, payload)
    assert service.list(org, facility) == []
    with pytest.raises(LookupError):
        service.get(org, facility, draft["id"])
    with pytest.raises(LookupError):
        service.approve(org, facility, "planner", draft["id"], 1)
    with pytest.raises(ValueError):
        service.save(org, facility, "planner", payload)


@pytest.mark.parametrize("mutation", ["missing", "shortage", "hold", "failed", "no_coa", "wrong_qa_scope", "unit"])
def test_source_validation(setup, mutation):
    engine, service, payload = setup
    with Session(engine) as session:
        lot = session.get(InventoryLot, "lot")
        qa = session.get(LotQualityEvidence, "lot")
        if mutation == "missing": payload["source_lot_id"] = "missing"
        if mutation == "shortage": payload["scenario"]["form"]["bulk_weight_value"] = 1001
        if mutation == "hold": lot.status = "quarantine"
        if mutation == "failed": qa.lab_testing_state = "failed"
        if mutation == "no_coa": qa.coa_reference = ""
        if mutation == "wrong_qa_scope": qa.facility_id = "other"
        if mutation == "unit": session.get(Product, "product").base_unit = "unit"
        session.commit()
    with pytest.raises(ValueError):
        save(service, payload)


def test_approval_revalidates_stock_and_qa_and_rolls_back(setup):
    engine, service, payload = setup
    draft = save(service, payload)
    with Session(engine) as session:
        session.get(LotQualityEvidence, "lot").lab_testing_state = "failed"
        session.commit()
    with pytest.raises(ValueError, match="QA"):
        service.approve("org", "facility", "planner", draft["id"], 1)
    assert service.get("org", "facility", draft["id"])["status"] == "draft"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProductionOrder)) == 0


def test_revision_guards_and_immutable_approved_plan(setup):
    _, service, payload = setup
    draft = save(service, payload)
    payload["revision"] = 1
    revised = service.save("org", "facility", "planner", payload, draft["id"])
    assert revised["revision"] == 2
    with pytest.raises(ValueError):
        service.save("org", "facility", "planner", payload, draft["id"])
    with pytest.raises(ValueError):
        service.approve("org", "facility", "planner", draft["id"], 1)
    service.approve("org", "facility", "planner", draft["id"], 2)
    payload["revision"] = 3
    with pytest.raises(ValueError):
        service.save("org", "facility", "planner", payload, draft["id"])


def test_execution_lifecycle_comes_from_canonical_order(setup):
    engine, service, payload = setup
    draft = save(service, payload)
    approved = service.approve("org", "facility", "planner", draft["id"], 1)
    for status, expected in [("in_progress", "executing"), ("on_hold", "executing"), ("complete", "completed"), ("cancelled", "cancelled")]:
        # Simulate the canonical executor's persisted transition, without posting inventory here.
        with engine.begin() as connection:
            connection.execute(ProductionOrder.__table__.update().where(ProductionOrder.id == approved["production_order_id"]).values(status=status))
        assert service.get("org", "facility", draft["id"])["status"] == expected
        assert service.list("org", "facility")[0]["status"] == expected


def test_draft_cancel_and_invalid_economics(setup):
    _, service, payload = setup
    draft = save(service, payload)
    assert service.cancel("org", "facility", "planner", draft["id"], 1)["status"] == "cancelled"
    with pytest.raises(ValueError): service.approve("org", "facility", "planner", draft["id"], 2)
    for field, value in [("bulk_weight_value", float("nan")), ("shrink_loss_pct", 101)]:
        bad = copy.deepcopy(payload)
        bad["scenario"]["form"][field] = value
        with pytest.raises(ValueError): save(service, bad)


def test_api_permissions_and_durable_detail(setup):
    engine, _, payload = setup
    app = FastAPI()
    app.include_router(router)
    context = RequestContext(user_id="actor", organization_id="org", facility_id="facility", role="planner")
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    created = client.post("/white-label/plans", json=payload)
    assert created.status_code == 200, created.text
    draft = created.json()
    assert client.get(f"/white-label/plans/{draft['id']}").json()["scenario"] == payload["scenario"]
    assert client.get("/white-label/sources").json()[0]["id"] == "lot"
    context = RequestContext(user_id="reader", organization_id="org", facility_id="facility", role="read_only")
    assert client.post("/white-label/plans", json=payload).status_code == 403
    assert client.post(f"/white-label/plans/{draft['id']}/approve", json={"revision": 1}).status_code == 403
    context = RequestContext(user_id="planner", organization_id="org", facility_id="other", role="planner")
    assert client.get(f"/white-label/plans/{draft['id']}").status_code == 404
    assert client.get("/white-label/sources").json() == []


def test_execution_handoff_commits_only_at_package_boundary(setup):
    engine, service, payload = setup
    draft = save(service, payload)
    approved = service.approve("org", "facility", "planner", draft["id"], 1)
    plan = PackageStudioPlan(action_type="pack_down", production_order_id=approved["production_order_id"],
        inputs=(PackageStudioInputPlan(lot_id="lot", quantity=100, unit="g"),),
        outputs=(PackageStudioOutputPlan(product_id="product", lot_code="PACKED-1", inventory_quantity=100,
            inventory_unit="g", source_equivalent_quantity=100, source_equivalent_unit="g"),), source_unit="g")
    with Session(engine) as session:
        session.get(LotQualityEvidence, "lot").lab_testing_state = "failed"
        session.commit()
    with pytest.raises(ValueError, match="QA"):
        PackageStudioService(engine).commit(plan, organization_id="org", facility_id="facility", actor="operator")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
        session.get(LotQualityEvidence, "lot").lab_testing_state = "passed"
        session.commit()
    result = PackageStudioService(engine).commit(plan, organization_id="org", facility_id="facility", actor="operator")
    assert len(result.output_lot_ids) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.sum(InventoryTransaction.quantity_delta)).where(InventoryTransaction.lot_id == "lot")) == 900
        output = session.get(InventoryLot, result.output_lot_ids[0])
        assert (output.organization_id, output.facility_id) == ("org", "facility")
    assert service.get("org", "facility", draft["id"])["status"] == "executing"
    assert service.list("org", "facility")[0]["status"] == "executing"
    retried = service.approve("org", "facility", "planner", draft["id"], 1)
    assert retried["production_order_id"] == approved["production_order_id"]
    assert retried["status"] == "executing"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProductionOrder)) == 1
        from modules.repack.models import WhiteLabelPlan
        assert session.get(WhiteLabelPlan, draft["id"]).status == "approved"


def test_existing_reservations_are_honored_at_approval(setup):
    engine, service, payload = setup
    draft = save(service, payload)
    with Session(engine) as session:
        order = ProductionOrder(organization_id="org", facility_id="facility", order_number="OTHER-RUN", work_type="internal",
            product_name="Other", product_format="bulk", requested_units=1, status="draft", created_by="planner", updated_by="planner")
        session.add(order)
        session.flush()
        session.add(MaterialReservation(organization_id="org", facility_id="facility", production_order_id=order.id,
            lot_id="lot", quantity=950, unit="g", status="reserved", reserved_by="planner"))
        session.commit()
    with pytest.raises(ValueError, match="available inventory"):
        service.approve("org", "facility", "planner", draft["id"], 1)


def test_migration_matches_model_and_refuses_destructive_downgrade(setup):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    from modules.repack.models import WhiteLabelPlan

    engine, service, payload = setup
    spec = importlib.util.spec_from_file_location("white_label_migration", "migrations/versions/0082_white_label_execution.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    WhiteLabelPlan.__table__.drop(engine)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    assert {column["name"] for column in inspect(engine).get_columns("white_label_plans")} == set(WhiteLabelPlan.__table__.columns.keys())
    save(service, payload)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        with pytest.raises(RuntimeError, match="Cannot discard"):
            migration.downgrade()


@pytest.mark.parametrize("mutation", ["facility", "organization", "hold", "no_coa", "wrong_qa_scope", "inactive", "unit", "ledger_unit", "quantity"])
def test_approval_rechecks_changed_source_without_posting_inventory(setup, mutation):
    engine, service, payload = setup
    draft = save(service, payload)
    with Session(engine) as session:
        lot = session.get(InventoryLot, "lot")
        quality = session.get(LotQualityEvidence, "lot")
        product = session.get(Product, "product")
        if mutation == "facility": lot.facility_id = "other"
        if mutation == "organization":
            # Simulate an externally corrupted reference, beyond ORM integrity hooks.
            session.execute(InventoryLot.__table__.update().where(InventoryLot.id == "lot").values(organization_id="outside"))
        if mutation == "hold": lot.status = "quarantine"
        if mutation == "no_coa": quality.coa_reference = ""
        if mutation == "wrong_qa_scope": quality.facility_id = "other"
        if mutation == "inactive": product.active = False
        if mutation == "unit": product.base_unit = "unit"
        if mutation == "ledger_unit": product.base_unit = "kg"
        if mutation == "quantity":
            session.add(InventoryTransaction(organization_id="org", facility_id="facility", lot_id="lot",
                transaction_type="adjustment", quantity_delta=-950, unit="g", actor="other-executor"))
        session.commit()
        count = session.scalar(select(func.count()).select_from(InventoryTransaction))
    with pytest.raises(ValueError):
        service.approve("org", "facility", "planner", draft["id"], 1)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProductionOrder)) == 0
        assert session.scalar(select(func.count()).select_from(MaterialReservation)) == 0
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == count
    assert service.get("org", "facility", draft["id"])["status"] == "draft"


def test_permission_allow_does_not_bypass_existing_role_or_capability(setup):
    from backend.app.routers.white_label import _scope
    from modules.coman.permissions import AppUserPermissionOverride
    from fastapi import HTTPException
    engine, _, _ = setup
    with Session(engine) as session:
        session.add(AppUserPermissionOverride(user_id="actor", organization_id="org", facility_id="facility",
            permission="white_label.manage_plans", effect="allow", created_by="admin", updated_by="admin"))
        session.commit()
    with pytest.raises(HTTPException) as denied:
        _scope(RequestContext("actor", "org", "facility", "read_only"), engine, write=True)
    assert denied.value.status_code == 403
    with Session(engine) as session:
        facility = session.get(Facility, "facility")
        facility.production_enabled = False
        facility.retail_enabled = True
        session.commit()
    with pytest.raises(HTTPException) as denied:
        _scope(RequestContext("actor", "org", "facility", "planner"), engine, write=True, approve=True)
    assert denied.value.status_code == 403


def test_crm_to_white_label_chain_and_empty_rollback_preserve_crm(setup):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    from modules.repack.models import WhiteLabelPlan
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_heads() == ["0083_onboarding_reporting"]
    revision = scripts.get_revision("0082_white_label_execution")
    assert revision.down_revision == "0081_wholesale_crm"
    assert scripts.get_revision(revision.down_revision).down_revision == "0080_doobie_work"
    engine, _, _ = setup
    WhiteLabelPlan.__table__.drop(engine)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        # The seeded model schema represents the integrated CRM candidate.
        before = set(inspect(connection).get_table_names())
        assert "commercial_quotes" in before
        revision.module.upgrade()
        assert set(inspect(connection).get_table_names()) == before | {"white_label_plans"}
        revision.module.downgrade()
        assert set(inspect(connection).get_table_names()) == before
        revision.module.upgrade()
        assert set(inspect(connection).get_table_names()) == before | {"white_label_plans"}


def test_postgres_rollback_locks_before_checking_evidence(monkeypatch):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from types import SimpleNamespace
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("0082_white_label_execution").module
    calls = []
    class Connection:
        dialect = SimpleNamespace(name="postgresql")
        def execute(self, statement):
            calls.append(str(statement))
            return SimpleNamespace(first=lambda: (1,))
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: Connection(),
        execute=lambda statement: calls.append(statement), drop_table=lambda table: pytest.fail("Evidence was dropped")))
    with pytest.raises(RuntimeError, match="Cannot discard"):
        migration.downgrade()
    assert calls == ["SET LOCAL lock_timeout = '5s'", "LOCK TABLE white_label_plans IN ACCESS EXCLUSIVE MODE",
                     "SELECT 1 FROM white_label_plans LIMIT 1"]


@pytest.mark.parametrize("mutation", ["cancelled", "complete", "on_hold", "no_coa", "unit", "commitment", "scope"])
def test_package_commit_revalidates_handoff_and_rolls_back(setup, mutation):
    from modules.package_studio.models import PackageStudioRun
    engine, service, payload = setup
    draft = save(service, payload)
    approved = service.approve("org", "facility", "planner", draft["id"], 1)
    with Session(engine) as session:
        order = session.get(ProductionOrder, approved["production_order_id"])
        if mutation in {"cancelled", "complete", "on_hold"}:
            session.execute(ProductionOrder.__table__.update().where(ProductionOrder.id == order.id).values(status=mutation))
        if mutation == "no_coa": session.get(LotQualityEvidence, "lot").coa_reference = ""
        if mutation == "unit": session.get(Product, "product").base_unit = "kg"
        if mutation == "scope":
            session.execute(ProductionOrder.__table__.update().where(ProductionOrder.id == order.id).values(facility_id="other"))
        if mutation == "commitment":
            other = ProductionOrder(organization_id="org", facility_id="facility", order_number="OTHER", work_type="internal",
                product_name="Other", product_format="bulk", requested_units=1, status="draft", created_by="planner", updated_by="planner")
            session.add(other)
            session.flush()
            session.add(MaterialReservation(organization_id="org", facility_id="facility", production_order_id=other.id,
                lot_id="lot", quantity=950, unit="g", status="reserved", reserved_by="planner"))
        session.commit()
    plan = PackageStudioPlan(action_type="pack_down", production_order_id=approved["production_order_id"],
        inputs=(PackageStudioInputPlan(lot_id="lot", quantity=100, unit="g"),),
        outputs=(PackageStudioOutputPlan(product_id="product", lot_code="OUTPUT", inventory_quantity=100,
            inventory_unit="g", source_equivalent_quantity=100, source_equivalent_unit="g"),), source_unit="g")
    with pytest.raises(ValueError):
        PackageStudioService(engine).commit(plan, organization_id="org", facility_id="facility", actor="operator")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PackageStudioRun)) == 0
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 1
