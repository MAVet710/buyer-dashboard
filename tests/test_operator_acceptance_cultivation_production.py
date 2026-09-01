from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Base, Facility
from services.demo_data import build_demo_payload


CLOSED_PRODUCTION_STATUSES = {"complete", "completed", "cancelled", "canceled", "failed"}


def _seeded_client(*, role: str = "dev", user_id: str = "operator-acceptance") -> tuple[TestClient, dict[str, str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    seeded = ensure_coman_demo_dataset(
        state={},
        actor="operator-acceptance-seed",
        payload=build_demo_payload(date(2026, 8, 31), scale="small"),
        engine=engine,
    )
    with Session(engine) as session, session.begin():
        facility = session.get(Facility, seeded["facility_id"])
        assert facility is not None
        facility.production_enabled = True
        facility.cultivation_enabled = True
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": seeded["organization_id"],
        "X-Facility-Id": seeded["facility_id"],
        "X-User-Id": user_id,
        "X-User-Role": role,
    }
    return TestClient(app, raise_server_exceptions=False), headers


def test_cultivation_operator_can_move_seedling_to_allocated_harvest_with_cost_and_lineage():
    client, headers = _seeded_client(role="operator", user_id="cultivation-floor-operator")
    try:
        for room_payload in (
            {
                "room_code": "OA-VEG-1",
                "display_name": "Operator Acceptance Veg",
                "phase": "vegetative",
                "plant_capacity": 24,
                "square_feet": 200,
                "target_cycle_days": 21,
                "active": True,
            },
            {
                "room_code": "OA-FLOWER-1",
                "display_name": "Operator Acceptance Flower",
                "phase": "flowering",
                "plant_capacity": 24,
                "square_feet": 300,
                "target_cycle_days": 63,
                "active": True,
            },
        ):
            room = client.post("/api/v1/inventory/production/plants/rooms", headers=headers, json=room_payload)
            assert room.status_code == 200, room.text

        created = client.post(
            "/api/v1/inventory/production/plants",
            headers=headers,
            json={
                "plant_tag": "OA-PLANT-0001",
                "strain_name": "Operator Kush",
                "phase": "seedling",
                "room_code": "OA-NURSERY",
                "planted_at": "2026-08-01",
                "estimated_harvest_date": "2026-10-31",
                "notes": "Stateful cultivation acceptance plant",
            },
        )
        assert created.status_code == 201, created.text
        plant_id = created.json()["id"]
        assert created.json()["phase"] == "seedling"

        invalid = client.post(
            f"/api/v1/inventory/production/plants/{plant_id}/transition",
            headers=headers,
            json={"phase": "flowering", "room_code": "OA-FLOWER-1", "reason": "Invalid shortcut probe"},
        )
        assert invalid.status_code == 422
        assert "cannot move from seedling to flowering" in invalid.text

        vegetative = client.post(
            f"/api/v1/inventory/production/plants/{plant_id}/transition",
            headers=headers,
            json={"phase": "vegetative", "room_code": "OA-VEG-1", "reason": "Seedling established"},
        )
        assert vegetative.status_code == 200, vegetative.text
        assert vegetative.json()["phase"] == "vegetative"
        flowering = client.post(
            f"/api/v1/inventory/production/plants/{plant_id}/transition",
            headers=headers,
            json={"phase": "flowering", "room_code": "OA-FLOWER-1", "reason": "Move to flower"},
        )
        assert flowering.status_code == 200, flowering.text
        assert flowering.json()["phase"] == "flowering"

        harvest = client.post(
            "/api/v1/inventory/production/plants/harvests",
            headers=headers,
            json={"harvest_code": "OA-HARVEST-0001", "plant_ids": [plant_id], "notes": "Stateful operator harvest"},
        )
        assert harvest.status_code == 201, harvest.text
        harvest_id = harvest.json()["id"]

        active = client.post(
            f"/api/v1/inventory/production/plants/harvests/{harvest_id}/transition",
            headers=headers,
            json={"status": "active", "wet_weight": 500, "waste_weight": 25, "unit": "g", "notes": "Cut and weighed"},
        )
        assert active.status_code == 200, active.text
        assert active.json()["wet_weight"] == 500
        assert active.json()["waste_weight"] == 25

        plants = client.get("/api/v1/inventory/production/plants?search=OA-PLANT-0001", headers=headers)
        assert plants.status_code == 200, plants.text
        assert plants.json()[0]["phase"] == "harvested"

        drying = client.post(
            f"/api/v1/inventory/production/plants/harvests/{harvest_id}/transition",
            headers=headers,
            json={"status": "drying", "dry_weight": 125, "unit": "g", "notes": "Dry weight recorded"},
        )
        assert drying.status_code == 200, drying.text
        assert drying.json()["dry_weight"] == 125
        assert drying.json()["dry_yield_pct"] == 25

        cost = client.post(
            "/api/v1/inventory/production/plants/costs",
            headers=headers,
            json={
                "entity_type": "harvest",
                "entity_id": harvest_id,
                "cost_type": "labor",
                "description": "Harvest labor",
                "quantity": 2,
                "unit": "hours",
                "unit_cost": 25,
                "notes": "Operator acceptance labor cost",
            },
        )
        assert cost.status_code == 201, cost.text
        assert cost.json()["amount"] == 50

        detail = client.get(f"/api/v1/inventory/production/plants/harvests/{harvest_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["labor_hours"] == 2
        assert detail.json()["labor_cost_usd"] == 50
        assert detail.json()["cost_per_dry_unit"] == 0.4

        premature_complete = client.post(
            f"/api/v1/inventory/production/plants/harvests/{harvest_id}/transition",
            headers=headers,
            json={"status": "completed", "unit": "g", "notes": "Premature closeout probe"},
        )
        assert premature_complete.status_code == 422
        assert "allocate" in premature_complete.text.casefold()
        assert "dry" in premature_complete.text.casefold()

        products = client.get("/api/v1/extraction/products", headers=headers)
        assert products.status_code == 200, products.text
        gram_product = next(row for row in products.json() if str(row["base_unit"]).casefold() == "g")
        allocation = {
            "outputs": [
                {
                    "product_id": gram_product["id"],
                    "lot_code": "OA-HARVEST-0001-DRY",
                    "quantity": 125,
                    "unit": "g",
                    "purpose": "finished_flower",
                    "measurement_basis": "dry",
                    "location_code": "HARVEST-OUTPUT",
                    "status": "quarantine",
                    "compliance_package_id": "",
                }
            ],
            "losses": [],
        }
        preview = client.post(
            f"/api/v1/inventory/production/plants/harvests/{harvest_id}/outputs/preview",
            headers=headers,
            json=allocation,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["blocker_count"] == 0
        dry_reconciliation = preview.json()["reconciliation"]["dry"]
        assert dry_reconciliation["measured"] == 125
        assert dry_reconciliation["allocated_after"] == 125
        assert dry_reconciliation["remaining"] == 0
        committed = client.post(
            f"/api/v1/inventory/production/plants/harvests/{harvest_id}/outputs/commit",
            headers=headers,
            json={**allocation, "preview_key": preview.json()["preview_key"]},
        )
        assert committed.status_code == 201, committed.text
        output_lot_id = committed.json()["output_lot_ids"][0]

        production_inventory = client.get("/api/v1/inventory/production/packages", headers=headers)
        assert production_inventory.status_code == 200, production_inventory.text
        harvested_lot = next(row for row in production_inventory.json()["items"] if row["id"] == output_lot_id)
        assert harvested_lot["on_hand"] == 125
        assert harvested_lot["status"].casefold() == "quarantine"

        lineage = client.get(f"/api/v1/material-lineage/lots/{output_lot_id}", headers=headers)
        assert lineage.status_code == 200, lineage.text
        assert harvest_id in str(lineage.json())
        assert plant_id in str(lineage.json())

        completed = client.post(
            f"/api/v1/inventory/production/plants/harvests/{harvest_id}/transition",
            headers=headers,
            json={"status": "completed", "unit": "g", "notes": "Dry output allocated and harvest closed"},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"

        events = client.get(f"/api/v1/inventory/production/plants/{plant_id}/events", headers=headers)
        assert events.status_code == 200, events.text
        event_types = [row["event_type"] for row in events.json()]
        assert event_types[0] == "created"
        assert event_types.count("phase_changed") == 2
        assert "harvest_assigned" in event_types
        assert "harvested" in event_types
    finally:
        app.dependency_overrides.clear()


def test_production_operator_can_execute_output_qa_release_cost_and_inventory_handoff():
    client, headers = _seeded_client(role="dev", user_id="production-lead")
    try:
        queue = client.get("/api/v1/production/orders", headers=headers)
        assert queue.status_code == 200, queue.text
        open_rows = [row for row in queue.json() if str(row["Status"]).casefold().replace(" ", "_") not in CLOSED_PRODUCTION_STATUSES]
        assert open_rows, "Operator acceptance seed must contain at least one open production order."
        order_id = open_rows[0]["order_id"]

        detail = client.get(f"/api/v1/production/orders/{order_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        order = detail.json()["order"]
        assert str(order["status"]).casefold() not in CLOSED_PRODUCTION_STATUSES

        reserve = client.post(f"/api/v1/production/orders/{order_id}/reserve", headers=headers)
        assert reserve.status_code == 200, reserve.text
        assert "reserved" in reserve.json()
        assert "shortages" in reserve.json()

        started = client.post(
            f"/api/v1/production/orders/{order_id}/events",
            headers=headers,
            json={
                "event_type": "started",
                "stage_key": "execution",
                "quantity": 0,
                "unit": "unit",
                "labor_hours": 0.5,
                "machine_hours": 0.25,
                "notes": "Stateful production acceptance start",
            },
        )
        assert started.status_code == 201, started.text

        held = client.post(
            f"/api/v1/production/orders/{order_id}/events",
            headers=headers,
            json={"event_type": "hold", "stage_key": "execution", "notes": "Acceptance production hold"},
        )
        assert held.status_code == 201, held.text
        held_detail = client.get(f"/api/v1/production/orders/{order_id}", headers=headers)
        assert held_detail.status_code == 200
        assert held_detail.json()["order"]["status"] == "on_hold"

        products = client.get("/api/v1/extraction/products", headers=headers)
        assert products.status_code == 200, products.text
        output_product = products.json()[0]
        planned_quantity = max(1.0, min(float(order["requested_units"] or 1), 10.0))

        output = client.post(
            f"/api/v1/production/orders/{order_id}/outputs",
            headers=headers,
            json={
                "product_id": output_product["id"],
                "planned_quantity": planned_quantity,
                "label": "Operator acceptance production output",
                "unit": output_product["base_unit"],
            },
        )
        assert output.status_code == 201, output.text
        output_id = output.json()["id"]

        actual_quantity = planned_quantity * 0.9
        actual = client.post(
            f"/api/v1/production/outputs/{output_id}/actual",
            headers=headers,
            json={"actual_quantity": actual_quantity, "lot_code": "OA-PRODUCTION-OUTPUT-0001"},
        )
        assert actual.status_code == 200, actual.text
        assert actual.json()["status"] == "quarantine"
        lot_id = actual.json()["lot_id"]
        assert lot_id

        cost = client.post(
            f"/api/v1/production/orders/{order_id}/costs",
            headers=headers,
            json={
                "category": "labor",
                "amount_usd": 20,
                "quantity": 1,
                "unit": "hour",
                "source_type": "operator_acceptance",
                "notes": "Production acceptance labor",
            },
        )
        assert cost.status_code == 201, cost.text

        failed = client.post(
            f"/api/v1/production/orders/{order_id}/qa",
            headers=headers,
            json={
                "event_type": "hold",
                "result": "failed",
                "output_id": output_id,
                "document_reference": "OA-QA-FAIL-PROBE",
                "notes": "Exercise failed QA state before controlled release",
            },
        )
        assert failed.status_code == 201, failed.text
        assert client.get(f"/api/v1/production/orders/{order_id}", headers=headers).json()["order"]["status"] == "on_hold"

        released = client.post(
            f"/api/v1/production/orders/{order_id}/qa",
            headers=headers,
            json={
                "event_type": "release",
                "result": "passed",
                "output_id": output_id,
                "document_reference": "OA-QA-PASS-0001",
                "notes": "QA release for acceptance output",
            },
        )
        assert released.status_code == 201, released.text

        production_inventory = client.get("/api/v1/inventory/production/packages", headers=headers)
        assert production_inventory.status_code == 200, production_inventory.text
        inventory_output = next(row for row in production_inventory.json()["items"] if row["id"] == lot_id)
        assert inventory_output["status"].casefold() == "available"
        assert inventory_output["on_hand"] == actual_quantity
        assert inventory_output["available"] == actual_quantity

        completed = client.post(
            f"/api/v1/production/orders/{order_id}/events",
            headers=headers,
            json={
                "event_type": "completed",
                "stage_key": "completion",
                "quantity": actual_quantity,
                "unit": output_product["base_unit"],
                "notes": "Acceptance production complete",
            },
        )
        assert completed.status_code == 201, completed.text

        final = client.get(f"/api/v1/production/orders/{order_id}", headers=headers)
        assert final.status_code == 200, final.text
        snapshot = final.json()
        assert snapshot["order"]["status"] == "complete"
        assert any(row["id"] == output_id and row["status"] == "released" for row in snapshot["outputs"])
        assert any(row["result"] == "failed" for row in snapshot["qa_events"])
        assert any(row["result"] == "passed" for row in snapshot["qa_events"])
        assert snapshot["cogs"]["total"] >= 20
        assert snapshot["actual_output"] >= actual_quantity
    finally:
        app.dependency_overrides.clear()


def test_production_floor_operator_cannot_self_approve_qa():
    client, headers = _seeded_client(role="operator", user_id="production-floor-operator")
    try:
        queue = client.get("/api/v1/production/orders", headers=headers)
        assert queue.status_code == 200 and queue.json()
        open_rows = [row for row in queue.json() if str(row["Status"]).casefold().replace(" ", "_") not in CLOSED_PRODUCTION_STATUSES]
        assert open_rows
        denied = client.post(
            f"/api/v1/production/orders/{open_rows[0]['order_id']}/qa",
            headers=headers,
            json={"event_type": "release", "result": "passed", "notes": "Unauthorized QA release probe"},
        )
        assert denied.status_code == 403
        assert "cannot post QA decisions" in denied.text
    finally:
        app.dependency_overrides.clear()
