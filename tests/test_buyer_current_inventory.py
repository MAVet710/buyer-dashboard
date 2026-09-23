from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, func
from sqlalchemy.orm import Session

from tests.test_ai_inventory_continuity import inventory_case  # noqa: F401
from backend.app.main import app
from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.services.buyer_current_inventory import current_buyer_inventory
from backend.app.services.ai_inventory import InventoryEvidenceUnavailable
from backend.app.services.inventory import InventoryQueryService
from modules.coman.models import InventoryLot, InventoryTransaction, DataHubImport


@pytest.fixture
def scoped_client(inventory_case):
    engine, context, _access = inventory_case
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {"X-Organization-Id": context.organization_id, "X-Facility-Id": context.facility_id,
               "X-User-Id": context.user_id, "X-User-Role": context.role}
    try:
        yield TestClient(app), headers
    finally:
        app.dependency_overrides.clear()


def test_current_buyer_matches_inventory_and_keeps_units_separate(inventory_case, scoped_client, monkeypatch):
    engine, context, _ = inventory_case
    monkeypatch.setattr("backend.app.routers.buyer_parity._model", lambda *args: pytest.fail("Current stock must not read uploaded forecasts"))
    client, headers = scoped_client
    response = client.get("/api/v1/buyer-parity/current-inventory?limit=1", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2 and body["has_more"] and len(body["items"]) == 1
    assert body["summary"]["product_count"] == 2  # Same display name, different IDs.
    assert body["summary"]["held_packages"] == 1
    totals = {row["unit"]: row for row in body["summary"]["totals_by_unit"]}
    assert totals["g"] == {"unit": "g", "on_hand": 100, "available": 85, "reserved": 15}
    assert totals["unit"] == {"unit": "unit", "on_hand": 8, "available": 0, "reserved": 0}
    assert body["sales_sources"]["state"] == "missing"
    second = client.get("/api/v1/buyer-parity/current-inventory?limit=1&offset=1", headers=headers).json()
    assert not second["has_more"]
    actual = {row["id"]: row for row in body["items"] + second["items"]}
    for item in InventoryQueryService(engine).list_packages(context.organization_id, context.facility_id, operation="retail").items:
        for key in ("product_id", "package_id", "unit", "on_hand", "available", "reserved", "status"):
            assert actual[item.id][key] == getattr(item, key)


def test_current_buyer_is_independent_of_upload_mode_and_has_safe_json(inventory_case, scoped_client):
    engine, _context, _ = inventory_case
    with Session(engine) as session, session.begin():
        session.get(InventoryLot, "lot-g").expiration_at = datetime(2026, 12, 1, tzinfo=timezone.utc)
    client, headers = scoped_client
    response = client.get("/api/v1/buyer-parity/current-inventory", headers={**headers, "X-DoobieLogic-Data-Mode": "Dutchie Live"})
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["items"]}
    assert rows["lot-g"]["expiration_at"] and rows["lot-unit"]["expiration_at"] is None
    assert rows["lot-unit"]["days_to_expiry"] is None
    assert "NaN" not in response.text


def test_current_buyer_separates_empty_filter_from_empty_inventory(inventory_case):
    engine, context, _ = inventory_case
    empty = current_buyer_inventory(replace(context, facility_id="facility-empty"), engine)
    assert empty["evidence"]["state"] == "empty" and empty["total"] == 0
    filtered = current_buyer_inventory(context, engine, search="no such package")
    assert filtered["evidence"]["state"] == "available" and filtered["total"] == 0
    held = current_buyer_inventory(context, engine, status="hold", unit="unit")
    assert [row["id"] for row in held["items"]] == ["lot-unit"]
    assert held["summary"]["totals_by_unit"] == [{"unit": "unit", "on_hand": 8, "available": 0, "reserved": 0}]


def test_current_buyer_rereads_committed_changes_without_mutating_records(inventory_case):
    engine, context, _ = inventory_case
    before = current_buyer_inventory(context, engine)
    with Session(engine) as session, session.begin():
        session.add(InventoryTransaction(organization_id=context.organization_id, facility_id=context.facility_id,
                    lot_id="lot-g", transaction_type="adjustment", quantity_delta=-10, unit="g", actor="qa", reason="Count"))
    after = current_buyer_inventory(context, engine)
    assert before["summary"]["totals_by_unit"][0]["available"] == 85
    assert after["summary"]["totals_by_unit"][0]["available"] == 75
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 6


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=10001", "search=" + "a" * 161])
def test_current_buyer_rejects_unbounded_reads(scoped_client, query):
    client, headers = scoped_client
    assert client.get(f"/api/v1/buyer-parity/current-inventory?{query}", headers=headers).status_code == 422


def test_current_buyer_enforces_real_scope_and_capabilities(inventory_case, scoped_client):
    engine, context, _ = inventory_case
    for wrong in (replace(context, organization_id="org-other"), replace(context, facility_id="facility-disabled")):
        with pytest.raises(InventoryEvidenceUnavailable):
            current_buyer_inventory(wrong, engine)
    client, headers = scoped_client
    assert client.get("/api/v1/buyer-parity/current-inventory", headers={**headers, "X-Organization-Id": "org-other"}).status_code == 403
    assert client.get("/api/v1/buyer-parity/current-inventory", headers={**headers, "X-Facility-Id": "facility-disabled"}).status_code == 403


def test_unavailable_inventory_is_503_without_secret_or_snapshot_fallback(inventory_case, scoped_client, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("synthetic-db-password-must-not-leak")
    monkeypatch.setattr(InventoryQueryService, "list_packages", failed)
    client, headers = scoped_client
    response = client.get("/api/v1/buyer-parity/current-inventory", headers=headers)
    assert response.status_code == 503
    assert "synthetic-db-password" not in response.text
    assert "zero stock" in response.text and "items" not in response.json()


def test_sales_metadata_is_secondary_scoped_and_does_not_fetch_payload(inventory_case, monkeypatch):
    engine, context, _ = inventory_case
    with Session(engine) as session, session.begin():
        for facility, filename in ((context.facility_id, "sales-here.csv"), ("facility-sibling", "sales-other.csv")):
            session.add(DataHubImport(organization_id=context.organization_id, facility_id=facility,
                dataset_key="product_sales", dataset_label="Sales", cache_key=facility, filename=filename,
                fingerprint=facility, payload_compressed=b"not-a-valid-compressed-file", payload_size=9,
                compressed_size=9, row_count=7, column_count=2, quality="Ready", status="active", imported_by="qa"))
    statements = []
    def capture(_conn, _cursor, statement, *_args): statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = current_buyer_inventory(context, engine)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert [row["filename"] for row in result["sales_sources"]["items"]] == ["sales-here.csv"]
    assert result["sales_sources"]["items"][0]["published_at"]
    assert not any("payload_compressed" in statement for statement in statements)
    def failed_session(*args, **kwargs): raise RuntimeError("private-metadata-error")
    monkeypatch.setattr("backend.app.services.buyer_current_inventory.Session", failed_session)
    degraded = current_buyer_inventory(context, engine)
    assert degraded["total"] == 2 and degraded["sales_sources"]["state"] == "unavailable"
    assert "private-metadata-error" not in str(degraded)


def test_oversized_inventory_is_refused_not_silently_truncated(inventory_case, monkeypatch):
    engine, context, _ = inventory_case
    monkeypatch.setattr("backend.app.services.ai_inventory.MAX_AI_INVENTORY_LOTS", 1)
    with pytest.raises(InventoryEvidenceUnavailable, match="bounded"):
        current_buyer_inventory(context, engine)


def test_uploaded_ai_slice_is_explicitly_historical(inventory_case, monkeypatch):
    from backend.app.routers import buyer_parity_actions as actions
    engine, context, _ = inventory_case
    source = SimpleNamespace(filename="old.csv", activated_at="2026-09-01")
    monkeypatch.setattr(actions, "_model", lambda *args: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), source, source))
    monkeypatch.setattr(actions, "sku_inventory_view", lambda *args: pd.DataFrame([{"product_name":"Old snapshot", "onhandunits":999, "days_of_supply":20, "dollars_on_hand":10}]))
    frame, provenance = actions._buyer_slice(actions.BuyerSliceRequest(), context, engine)
    assert len(frame) == 1 and provenance["classification"] == "uploaded_historical_snapshot"
    assert provenance["current_inventory"] is False
    assert provenance["sales_published_at"] == "2026-09-01"
    assert "not current stock" in provenance["interpretation"]


def test_query_count_stays_constant_as_packages_grow(inventory_case):
    engine, context, _ = inventory_case
    def read_count():
        statements = []
        def capture(_conn, _cursor, statement, *_args): statements.append(statement)
        event.listen(engine, "before_cursor_execute", capture)
        try:
            result = current_buyer_inventory(context, engine)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        return len(statements), result
    baseline, _ = read_count()
    with Session(engine) as session, session.begin():
        for index in range(65):
            lot = InventoryLot(id=f"scale-{index}", organization_id=context.organization_id,
                               facility_id=context.facility_id, product_id="product-g",
                               lot_code=f"SCALE-{index}", status="available")
            session.add(lot); session.flush()
            session.add(InventoryTransaction(organization_id=context.organization_id, facility_id=context.facility_id,
                        lot_id=lot.id, transaction_type="receive", quantity_delta=1, unit="g", actor="qa"))
    scaled, result = read_count()
    assert scaled <= baseline + 1
    assert result["total"] == 67 and len(result["items"]) == 50 and result["has_more"]
    assert result["summary"]["totals_by_unit"][0]["on_hand"] == 165


def test_live_mode_still_blocks_uploaded_forecasts_and_cannot_bypass_scope(scoped_client):
    client, headers = scoped_client
    live = {**headers, "X-DoobieLogic-Data-Mode": "Dutchie Live"}
    for path in ("dashboard", "legacy-overview", "uploaded-source-evidence"):
        assert client.get(f"/api/v1/buyer-parity/{path}", headers=live).status_code == 409
    for path in ("inventory-check", "buyer-brief", "current-inventory"):
        assert client.post(f"/api/v1/buyer-parity/{path}", headers=live, json={}).status_code == 409
    assert client.get("/api/v1/buyer-parity/current-inventory", headers={**live, "X-Organization-Id": "org-other"}).status_code == 403
