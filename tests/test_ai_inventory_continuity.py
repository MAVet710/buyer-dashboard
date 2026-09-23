from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Load the real application model graph without entering its lifespan.
from backend.app.main import app
from backend.app.auth import RequestContext, get_authorization_engine
from backend.app.database import get_engine
from backend.app.services.ai_datasets import build_dataset_registry, facility_access
from backend.app.services.ai_inventory import (
    CurrentInventoryObservation, INVENTORY_COLUMNS, InventoryEvidenceUnavailable,
)
from backend.app.services.inventory import InventoryQueryService
from modules.coman.models import (
    Base, Facility, InventoryLot, InventoryTransaction, MaterialReservation,
    Organization, Product, ProductionOrder,
)
from modules.product_master.models import ProductMasterProfile
from services.ai.datasets import DatasetRegistry


@pytest.fixture
def inventory_case():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    context = RequestContext(user_id="qa-inventory", organization_id="org-one", facility_id="facility-one", role="buyer")
    with Session(engine) as session, session.begin():
        session.add_all([
            Organization(id="org-one", name="Inventory QA", slug="inventory-qa"),
            Organization(id="org-other", name="Other QA", slug="inventory-other-qa"),
        ])
        session.flush()
        session.add_all([
            Facility(id="facility-one", organization_id="org-one", name="One", code="ONE", retail_enabled=True, production_enabled=True),
            Facility(id="facility-sibling", organization_id="org-one", name="Sibling", code="SIBLING", retail_enabled=True),
            Facility(id="facility-empty", organization_id="org-one", name="Empty", code="EMPTY", retail_enabled=True),
            Facility(id="facility-disabled", organization_id="org-one", name="Disabled", code="DISABLED", retail_enabled=False),
            Facility(id="facility-other", organization_id="org-other", name="Other", code="OTHER", retail_enabled=True),
            Product(id="product-g", organization_id="org-one", name="Same display name", sku="GRAMS", item_type="cannabis", base_unit="g", unit_cost=2),
            Product(id="product-unit", organization_id="org-one", name="Same display name", sku="UNITS", item_type="finished_good", base_unit="unit", unit_cost=10),
            Product(id="product-production", organization_id="org-one", name="Production only", sku="PROD", item_type="cannabis", base_unit="g"),
            Product(id="product-other", organization_id="org-other", name="Other tenant", sku="OTHER", item_type="cannabis", base_unit="g"),
        ])
        session.flush()
        session.add(ProductMasterProfile(product_id="product-production", organization_id="org-one", retail_enabled=False, production_enabled=True))
        for lot_id, org, facility, product, quantity, unit, status in (
            ("lot-g", "org-one", "facility-one", "product-g", 100, "g", "available"),
            ("lot-unit", "org-one", "facility-one", "product-unit", 8, "unit", "hold"),
            ("lot-production", "org-one", "facility-one", "product-production", 7, "g", "available"),
            ("lot-sibling", "org-one", "facility-sibling", "product-g", 77, "g", "available"),
            ("lot-other", "org-other", "facility-other", "product-other", 88, "g", "available"),
        ):
            session.add(InventoryLot(id=lot_id, organization_id=org, facility_id=facility, product_id=product, lot_code=lot_id, compliance_package_id=f"QA-{lot_id}", status=status))
            session.flush()
            session.add(InventoryTransaction(organization_id=org, facility_id=facility, lot_id=lot_id, transaction_type="receive", quantity_delta=quantity, unit=unit, actor="qa"))
        order = ProductionOrder(id="qa-order", organization_id="org-one", facility_id="facility-one", order_number="QA-ORDER", work_type="internal", product_name="QA output", sku="QA", product_format="bulk", requested_units=1, status="scheduled", created_by="qa", updated_by="qa")
        session.add(order)
        session.flush()
        session.add(MaterialReservation(organization_id="org-one", facility_id="facility-one", production_order_id=order.id, lot_id="lot-g", quantity=15, unit="g", status="reserved", reserved_by="qa"))
    access, *_ = facility_access(context, engine, operation_type="retail")
    yield engine, context, access
    engine.dispose()


def subset(context, engine, access, keys, agent="inventory"):
    # Exercise the production registry's loaders and sanitization, not copies of
    # their implementation, while avoiding unrelated agent datasets in a unit test.
    complete = build_dataset_registry(context, engine)
    registry = DatasetRegistry()
    for spec in complete.specs_for_agent(agent, access):
        if spec.key in keys:
            registry.register(spec)
    return registry


@pytest.mark.parametrize("agent", ["inventory", "buyer", "purchasing", "ops"])
def test_inventory_ai_matches_workspace_without_uploads(inventory_case, monkeypatch, agent):
    engine, context, access = inventory_case
    def no_uploaded_forecast(*args):
        pytest.fail("Current inventory must not depend on uploaded forecast data")
    monkeypatch.setattr("backend.app.services.ai_datasets._model", no_uploaded_forecast)
    registry = subset(context, engine, access, {"inventory", "inventory_evidence"}, agent)
    loaded = registry.load_for_agent(agent, access)
    actual = loaded["inventory"].frame.set_index("id")
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    try:
        response = TestClient(app).get("/api/v1/inventory/retail/packages", headers={"X-Organization-Id": context.organization_id, "X-Facility-Id": context.facility_id, "X-User-Id": context.user_id, "X-User-Role": context.role})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    expected = {row["id"]: row for row in response.json()["items"]}
    assert set(actual.index) == set(expected) == {"lot-g", "lot-unit"}
    for lot_id, row in expected.items():
        for column in ("package_id", "product_id", "sku", "unit", "on_hand", "available", "reserved", "production_reserved", "status", "location"):
            assert actual.loc[lot_id, column] == row[column]
    assert actual.loc["lot-g", "on_hand"] == 100
    assert actual.loc["lot-g", "available"] == 85
    assert actual.loc["lot-g", "reserved"] == 15
    assert actual.loc["lot-unit", "unit"] == "unit"
    assert actual.loc["lot-unit", "available"] == 0
    assert actual["product_name"].nunique() == 1  # Duplicate names never merge IDs or units.
    evidence = loaded["inventory_evidence"].frame.iloc[0]
    assert evidence["state"] == "available" and evidence["row_count"] == 2
    assert evidence["observed_at"] and "Not verified" in evidence["provider_freshness"]
    assert "sold_30d" not in actual.columns and "daily_velocity" not in actual.columns


def test_new_request_observes_committed_adjustment_without_mutating_stock(inventory_case):
    engine, context, access = inventory_case
    first = CurrentInventoryObservation(context, engine)
    assert first.inventory(access).set_index("id").loc["lot-g", "on_hand"] == 100
    with Session(engine) as session, session.begin():
        session.add(InventoryTransaction(organization_id="org-one", facility_id="facility-one", lot_id="lot-g", transaction_type="adjustment", quantity_delta=-10, unit="g", actor="qa", reason="Synthetic correction"))
    second = CurrentInventoryObservation(context, engine).inventory(access).set_index("id")
    assert second.loc["lot-g", "on_hand"] == 90
    assert second.loc["lot-g", "available"] == 75
    # One request has a stable observation, the next request gets fresh stock.
    assert first.inventory(access).set_index("id").loc["lot-g", "on_hand"] == 100
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 6


def test_valid_empty_is_not_unavailable(inventory_case):
    engine, context, access = inventory_case
    context = replace(context, facility_id="facility-empty")
    access = replace(access, facility_id="facility-empty")
    observation = CurrentInventoryObservation(context, engine)
    assert observation.inventory(access).empty
    assert tuple(observation.inventory(access).columns) == INVENTORY_COLUMNS
    evidence = observation.evidence(access).iloc[0]
    assert evidence["state"] == "empty" and evidence["row_count"] == 0


def test_database_failure_is_unknown_not_zero_and_does_not_expose_exception(inventory_case, monkeypatch):
    engine, context, access = inventory_case
    calls = []
    def broken(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("synthetic-connection-secret-marker")
    monkeypatch.setattr(InventoryQueryService, "list_packages", broken)
    registry = subset(context, engine, access, {"inventory", "inventory_evidence"})
    loaded = registry.load_for_agent("inventory", access)
    assert "inventory" not in loaded
    evidence = loaded["inventory_evidence"].frame.iloc[0]
    assert evidence["state"] == "unavailable" and pd.isna(evidence["row_count"])
    assert pd.isna(evidence["observed_at"])
    assert "synthetic-connection-secret-marker" not in str(evidence.to_dict())
    assert calls == [1]


def test_cached_observation_rejects_other_scope_and_missing_capability(inventory_case):
    engine, context, access = inventory_case
    observation = CurrentInventoryObservation(context, engine)
    observation.inventory(access)
    for wrong in (
        replace(access, facility_id="facility-sibling"),
        replace(access, organization_id="org-other", facility_id="facility-other"),
        replace(access, organization_id=""),
        replace(access, capabilities=frozenset()),
    ):
        with pytest.raises(InventoryEvidenceUnavailable):
            observation.inventory(wrong)
        with pytest.raises(InventoryEvidenceUnavailable):
            observation.evidence(wrong)


@pytest.mark.parametrize("organization,facility", [("org-one", "facility-other"), ("org-one", "facility-disabled"), ("org-one", "missing")])
def test_database_scope_and_retail_capability_are_checked(inventory_case, organization, facility):
    engine, context, access = inventory_case
    context = replace(context, organization_id=organization, facility_id=facility)
    access = replace(access, organization_id=organization, facility_id=facility)
    observation = CurrentInventoryObservation(context, engine)
    with pytest.raises(InventoryEvidenceUnavailable):
        observation.inventory(access)
    assert observation.evidence(access).iloc[0]["state"] == "unavailable"


def test_oversized_inventory_is_not_silently_truncated(inventory_case, monkeypatch):
    engine, context, access = inventory_case
    monkeypatch.setattr("backend.app.services.ai_inventory.MAX_AI_INVENTORY_LOTS", 2)
    monkeypatch.setattr(InventoryQueryService, "list_packages", lambda *a, **k: pytest.fail("Oversized facility must be refused before hydration"))
    observation = CurrentInventoryObservation(context, engine)
    with pytest.raises(InventoryEvidenceUnavailable):
        observation.inventory(access)
    evidence = observation.evidence(access).iloc[0]
    assert evidence["state"] == "too_large" and pd.isna(evidence["row_count"])


def test_current_and_uploaded_inventory_are_explicitly_separate(inventory_case, monkeypatch):
    engine, context, access = inventory_case
    calls = []
    inventory_source = SimpleNamespace(filename="old-inventory.csv", row_count=1, activated_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    sales_source = SimpleNamespace(filename="sales.csv", row_count=1, activated_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    def uploaded(*args):
        calls.append(1)
        snapshot = pd.DataFrame([{"itemname": "Old product", "onhandunits": 9999}])
        return pd.DataFrame(), pd.DataFrame(), snapshot, pd.DataFrame([{"unitssold": 2}]), inventory_source, sales_source
    monkeypatch.setattr("backend.app.services.ai_datasets._model", uploaded)
    keys = {"inventory", "inventory_evidence", "buyer_inventory_snapshot", "sales", "buyer_sources"}
    registry = subset(context, engine, access, keys)
    loaded = registry.load_for_agent("inventory", access)
    assert loaded["inventory"].frame.set_index("id").loc["lot-g", "on_hand"] == 100
    assert loaded["buyer_inventory_snapshot"].frame.iloc[0]["onhandunits"] == 9999
    sources = loaded["buyer_sources"].frame.set_index("dataset")
    assert sources.loc["buyer_inventory_snapshot", "filename"] == "old-inventory.csv"
    assert sources.loc["sales", "filename"] == "sales.csv"
    assert sources.loc["buyer_inventory_snapshot", "freshness"] != sources.loc["sales", "freshness"]
    assert calls == [1]


def test_missing_forecast_does_not_become_zero_sales_or_missing_current_stock(inventory_case, monkeypatch):
    engine, context, access = inventory_case
    calls = []
    def missing(*args):
        calls.append(1)
        raise ValueError("synthetic-upload-secret-marker")
    monkeypatch.setattr("backend.app.services.ai_datasets._model", missing)
    keys = {"inventory", "inventory_evidence", "buyer_inventory_snapshot", "sales", "buyer_forecast", "buyer_product_forecast", "buyer_sources"}
    loaded = subset(context, engine, access, keys).load_for_agent("inventory", access)
    assert set(loaded) == {"inventory", "inventory_evidence", "buyer_sources"}
    sources = loaded["buyer_sources"].frame
    assert set(sources["state"]) == {"unavailable"} and sources["rows"].isna().all()
    assert "synthetic-upload-secret-marker" not in sources.to_json()
    assert calls == [1]


def test_inventory_observation_is_read_only_and_query_count_does_not_grow_per_lot(inventory_case):
    engine, context, access = inventory_case
    def statements_for_read():
        statements = []
        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement)
        event.listen(engine, "before_cursor_execute", capture)
        try:
            observation = CurrentInventoryObservation(context, engine)
            observation.inventory(access)
            observation.evidence(access)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        return len(statements)
    small = statements_for_read()
    with Session(engine) as session, session.begin():
        for index in range(40):
            lot = InventoryLot(id=f"many-{index}", organization_id="org-one", facility_id="facility-one", product_id="product-unit", lot_code=f"MANY-{index}", status="available")
            session.add(lot)
            session.flush()
            session.add(InventoryTransaction(organization_id="org-one", facility_id="facility-one", lot_id=lot.id, transaction_type="receive", quantity_delta=1, unit="unit", actor="qa"))
    assert statements_for_read() == small


def test_unrelated_audit_fields_remain_available(inventory_case):
    engine, context, access = inventory_case
    specs = {row.key: row for row in build_dataset_registry(context, engine).specs_for_agent("inventory", access)}
    assert "created_at" in specs["inventory_audits"].allowed_columns
