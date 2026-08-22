from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, MachineModel, Organization


ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="Co-Man Web QA", slug="coman-web-qa")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Production One",
            code="PROD-1",
            production_enabled=True,
            retail_enabled=False,
        )
        other_facility = Facility(
            organization_id=organization.id,
            name="Production Two",
            code="PROD-2",
            production_enabled=True,
            retail_enabled=False,
        )
        model = MachineModel(
            manufacturer="Parity Machines",
            model="PM-100",
            category="flower_packaging",
            published_max_rate=500,
            rate_unit="units/hour",
            published_min_operators=1,
            planning_utilization_pct=65,
            source_url="https://example.test/pm-100",
        )
        session.add_all([facility, other_facility, model])
        session.commit()
        return engine, organization.id, facility.id, other_facility.id, model.id


def _headers(organization_id: str, facility_id: str) -> dict[str, str]:
    return {
        "X-Organization-Id": organization_id,
        "X-Facility-Id": facility_id,
        "X-User-Id": "dev-user",
        "X-User-Role": "dev",
    }


def test_react_coman_page_preserves_streamlit_tabs_controls_and_defaults():
    page = (ROOT / "frontend" / "src" / "pages" / "ProductionPage.tsx").read_text(encoding="utf-8")
    for label in [
        "Dashboard",
        "New Job",
        "Schedule",
        "Resources",
        "Inventory & BOM",
        "Customers",
        "Performance",
        "Open Orders",
        "Units Planned",
        "External Jobs",
        "Setup readiness",
        "Current production queue",
        "Duplicate recurring job",
        "Weight-based production recommendation",
        "Available bulk weight",
        "Expected process loss %",
        "Loaded labor cost $/hour",
        "Product / SKU",
        "Max Allocation %",
        "Committed production order",
        "Create production order",
        "Crew availability",
        "Required downstream hand labor",
        "Browse benchmark library",
        "Required hand-labor area",
        "Product and material control",
        "Add a product or material",
        "Receive a lot",
        "Post inventory movement",
        "Reserve material for a job",
        "Bill of materials",
        "Inventory ledger",
        "Co-Man customers",
        "Record completed-job actuals",
        "Performance visuals",
        "Export Production Ops Report",
        "Production Control",
        "Open Production 360",
        "Reserve BOM materials",
        "Record stage / actuals",
        "Outputs + QA",
        "Add COGS",
        "Post actual to quarantine",
        "Record QA",
    ]:
        assert label in page
    assert "useState(10)" in page
    assert 'useState("Pounds")' in page
    assert "useState(5)" in page
    assert "useState(22)" in page
    assert "shift_hours: 8" in page
    assert "[unitsCase, setUnitsCase] = useState(100)" in page
    assert "coman-parity/workspace" in page


def test_coman_parity_api_persists_the_complete_streamlit_workflow():
    engine, organization_id, facility_id, other_facility_id, machine_model_id = _fixture()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    headers = _headers(organization_id, facility_id)
    try:
        workspace = client.get("/api/v1/coman-parity/workspace", headers=headers)
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["metrics"] == {
            "open_orders": 0,
            "units_planned": 0,
            "external_jobs": 0,
            "customers": 0,
        }
        assert len(workspace.json()["readiness"]) == 4

        customer = client.post(
            "/api/v1/coman-parity/customers",
            headers=headers,
            json={
                "name": "Partner Cannabis",
                "license_or_registration": "MFG-123",
                "contact_name": "Pat Partner",
                "contact_email": "pat@example.test",
            },
        )
        assert customer.status_code == 201, customer.text
        customer_id = customer.json()["id"]

        bulk = client.post(
            "/api/v1/coman-parity/products",
            headers=headers,
            json={"sku": "BULK-1", "name": "Bulk Flower", "item_type": "cannabis", "base_unit": "g", "unit_cost": 1.5},
        )
        finished = client.post(
            "/api/v1/coman-parity/products",
            headers=headers,
            json={"sku": "FG-35", "name": "Flower 3.5g", "item_type": "finished_good", "base_unit": "each", "unit_cost": 7.5},
        )
        assert bulk.status_code == 201, bulk.text
        assert finished.status_code == 201, finished.text

        lot = client.post(
            "/api/v1/coman-parity/lots",
            headers=headers,
            json={
                "product_id": bulk.json()["id"],
                "lot_code": "BULK-LOT-1",
                "compliance_package_id": "1A406TEST",
                "location_code": "VAULT",
                "opening_quantity": 1000,
                "unit": "g",
            },
        )
        assert lot.status_code == 201, lot.text
        lot_id = lot.json()["id"]

        order = client.post(
            "/api/v1/coman-parity/orders",
            headers=headers,
            json={
                "order_number": "COM-000001",
                "work_type": "external",
                "requested_units": 100,
                "product_name": "Flower 3.5g",
                "product_format": "pouched flower — 3.5 g",
                "sku": "FG-35",
                "customer_id": customer_id,
                "due_date": date.today().isoformat(),
                "priority": "high",
                "source_lot_reference": "BULK-LOT-1",
                "material_owner": "customer",
                "packaging_owner": "internal",
                "notes": "Parity order",
            },
        )
        assert order.status_code == 201, order.text
        order_id = order.json()["id"]

        machine = client.post(
            "/api/v1/coman-parity/machines",
            headers=headers,
            json={
                "machine_model_id": machine_model_id,
                "asset_code": "PK-01",
                "display_name": "Primary Packager",
                "effective_rate": 400,
                "preferred_crew_size": 3,
                "setup_minutes": 30,
                "cleanup_minutes": 30,
            },
        )
        assert machine.status_code == 201, machine.text

        hand = client.post(
            "/api/v1/coman-parity/hand-labor",
            headers=headers,
            json={
                "default_crew_size": 4,
                "sticker_units_per_person_hour": 100,
                "case_pack_units_per_person_hour": 120,
                "final_cases_per_person_hour": 10,
                "setup_minutes": 15,
                "cleanup_minutes": 20,
            },
        )
        assert hand.status_code == 200, hand.text

        movement = client.post(
            "/api/v1/coman-parity/movements",
            headers=headers,
            json={"lot_id": lot_id, "transaction_type": "adjustment_out", "quantity": 50, "unit": "g", "reason": "QA adjustment"},
        )
        reservation = client.post(
            "/api/v1/coman-parity/reservations",
            headers=headers,
            json={"production_order_id": order_id, "lot_id": lot_id, "quantity": 350, "unit": "g"},
        )
        bom = client.post(
            "/api/v1/coman-parity/boms",
            headers=headers,
            json={
                "output_product_id": finished.json()["id"],
                "output_quantity": 1,
                "expected_loss_pct": 3,
                "components": [{"input_product_id": bulk.json()["id"], "quantity": 3.5, "unit": "g"}],
            },
        )
        assert movement.status_code == 201, movement.text
        assert reservation.status_code == 201, reservation.text
        assert bom.status_code == 201, bom.text

        crew = client.post(
            "/api/v1/coman-parity/crew",
            headers=headers,
            json={"work_date": date.today().isoformat(), "shift_name": "Day", "available_people": 6, "shift_hours": 8, "notes": "Full crew"},
        )
        capacity = client.post(
            "/api/v1/coman-parity/capacity",
            headers=headers,
            json={"requested_units": 100, "effective_rate": 400, "crew_size": 3, "setup_minutes": 30, "cleanup_minutes": 30, "shift_hours": 8, "units_per_case": 100},
        )
        assert crew.status_code == 200, crew.text
        assert capacity.status_code == 200, capacity.text
        assert capacity.json()["hand"] is not None

        optimizer = client.post(
            "/api/v1/coman-parity/optimizer",
            headers=headers,
            json={
                "bulk_weight": 10,
                "bulk_unit": "Pounds",
                "expected_loss_pct": 5,
                "optimization_goal": "Maximum total profit",
                "labor_rate": 22,
                "products": [{
                    "eligible": True,
                    "product": "3.5 g flower pouch",
                    "format": "Pouched flower — 3.5 g",
                    "unit_size_g": 3.5,
                    "revenue_per_unit": 18,
                    "bulk_cost_per_g": 1.5,
                    "packaging_cost_per_unit": 0.75,
                    "other_cost_per_unit": 0.1,
                    "machine_units_per_hour": 900,
                    "machine_crew": 3,
                    "machine_cost_per_hour": 35,
                    "units_per_case": 50,
                    "max_allocation_pct": 100,
                }],
            },
        )
        assert optimizer.status_code == 200, optimizer.text
        assert optimizer.json()["recommendations"]
        assert optimizer.json()["rates_ready"] is True
        prefill = client.post(
            "/api/v1/coman-parity/optimizer/prefill",
            headers=headers,
            json={"recommendation": optimizer.json()["recommendations"][0], "work_type_label": "Internal / owned product"},
        )
        assert prefill.status_code == 200, prefill.text
        assert prefill.json()["requested_units"] > 0

        production_reserve = client.post(
            f"/api/v1/production/orders/{order_id}/reserve",
            headers=headers,
            json={},
        )
        production_event = client.post(
            f"/api/v1/production/orders/{order_id}/events",
            headers=headers,
            json={"event_type": "measurement", "quantity": 100, "labor_hours": 1.5, "machine_hours": 0.5, "notes": "Stage measurement"},
        )
        production_output = client.post(
            f"/api/v1/production/orders/{order_id}/outputs",
            headers=headers,
            json={"product_id": finished.json()["id"], "planned_quantity": 100, "label": "Flower 3.5g", "unit": "each"},
        )
        assert production_reserve.status_code == 200, production_reserve.text
        assert production_event.status_code == 201, production_event.text
        assert production_output.status_code == 201, production_output.text
        output_id = production_output.json()["id"]
        assert production_output.json()["position"] == 1
        assert production_output.json()["product_id"] == finished.json()["id"]
        output_actual = client.post(
            f"/api/v1/production/outputs/{output_id}/actual",
            headers=headers,
            json={"actual_quantity": 98, "lot_code": "COM-000001-1"},
        )
        output_qa = client.post(
            f"/api/v1/production/orders/{order_id}/qa",
            headers=headers,
            json={"event_type": "release", "result": "passed", "output_id": output_id},
        )
        production_cost = client.post(
            f"/api/v1/production/orders/{order_id}/costs",
            headers=headers,
            json={"category": "labor", "amount_usd": 125, "notes": "Completed labor"},
        )
        assert output_actual.status_code == 200, output_actual.text
        assert output_qa.status_code == 201, output_qa.text
        assert production_cost.status_code == 201, production_cost.text
        production_detail = client.get(
            f"/api/v1/production/orders/{order_id}", headers=headers
        )
        assert production_detail.status_code == 200, production_detail.text
        assert production_detail.json()["outputs"][0]["position"] == 1
        assert production_detail.json()["outputs"][0]["product_id"] == finished.json()["id"]
        assert production_detail.json()["outputs"][0]["status"] == "released"
        assert production_detail.json()["cogs"]["total"] == 125

        status = client.post(
            f"/api/v1/coman-parity/orders/{order_id}/status",
            headers=headers,
            json={"status": "scheduled"},
        )
        duplicate = client.post(
            f"/api/v1/coman-parity/orders/{order_id}/duplicate",
            headers=headers,
            json={"new_order_number": "COM-000002"},
        )
        actual = client.post(
            f"/api/v1/coman-parity/orders/{order_id}/actuals",
            headers=headers,
            json={"actual_units": 98, "scrap_units": 1, "rework_units": 1, "actual_machine_hours": 1.25, "actual_labor_hours": 5.5, "notes": "Completed"},
        )
        assert status.status_code == 200, status.text
        assert duplicate.status_code == 201, duplicate.text
        assert actual.status_code == 200, actual.text

        workspace = client.get("/api/v1/coman-parity/workspace", headers=headers)
        assert workspace.status_code == 200, workspace.text
        body = workspace.json()
        assert len(body["orders"]) == 2
        assert body["metrics"]["open_orders"] == 1
        assert body["metrics"]["external_jobs"] == 2
        assert next(row for row in body["lots"] if row["id"] == lot_id)["on_hand"] == 950
        assert len(body["reservations"]) == 1
        assert len(body["actuals"]) == 1
        assert len(body["machines"]) == 1
        assert len(body["crew"]) == 1

        isolated = client.get(
            "/api/v1/coman-parity/workspace",
            headers=_headers(organization_id, other_facility_id),
        )
        assert isolated.status_code == 200, isolated.text
        assert isolated.json()["orders"] == []
        assert isolated.json()["lots"] == []

        report = client.get("/api/v1/coman-parity/report.pdf", headers=headers)
        assert report.status_code == 200, report.text
        assert report.headers["content-type"] == "application/pdf"
        assert report.content.startswith(b"%PDF")
        assert len(report.content) > 1000
    finally:
        app.dependency_overrides.clear()
