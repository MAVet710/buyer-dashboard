from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Base
from services.demo_data import build_demo_payload


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
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": seeded["organization_id"],
        "X-Facility-Id": seeded["facility_id"],
        "X-User-Id": user_id,
        "X-User-Role": role,
    }
    return TestClient(app, raise_server_exceptions=False), headers


def test_retail_operator_can_receive_sell_audit_pause_resume_and_export():
    """Use Retail Ops as an operator instead of only proving that its pages boot."""

    client, headers = _seeded_client(role="operator", user_id="retail-floor-operator")
    try:
        before = client.get("/api/v1/inventory/retail/packages", headers=headers)
        assert before.status_code == 200, before.text
        source_items = [row for row in before.json()["items"] if row["available"] > 0]
        assert source_items, "Operator acceptance seed must expose at least one sellable/available retail item."
        source = source_items[0]

        package_id = "1A4-OA-RETAIL-0001"
        receipt_payload = {
            "product_id": source["product_id"],
            "lot_code": "OA-RETAIL-LOT-0001",
            "package_id": package_id,
            "quantity": 12,
            "unit": source["unit"],
            "location": "RETAIL-VAULT-A",
            "source_name": "Operator Acceptance Vendor",
            "manifest_reference": "OA-MANIFEST-0001",
            "lab_testing_state": "TestPassed",
            "coa_reference": "OA-COA-0001",
            "notes": "Stateful Retail Ops operator acceptance receipt",
        }
        received = client.post("/api/v1/inventory/retail/receipts", headers=headers, json=receipt_payload)
        assert received.status_code == 201, received.text
        received_lot_id = received.json()["lot_id"]
        assert received.json()["operation"] == "retail"
        assert received.json()["status"] == "available"

        duplicate = client.post("/api/v1/inventory/retail/receipts", headers=headers, json=receipt_payload)
        assert duplicate.status_code == 409, duplicate.text

        after_receipt = client.get("/api/v1/inventory/retail/packages", headers=headers)
        assert after_receipt.status_code == 200, after_receipt.text
        package = next(row for row in after_receipt.json()["items"] if row["package_id"] == package_id)
        assert package["id"] == received_lot_id
        assert package["on_hand"] == 12
        assert package["available"] == 12
        assert package["location"] == "RETAIL-VAULT-A"
        assert package["source_name"] == "Operator Acceptance Vendor"

        history = client.get("/api/v1/inventory/retail/receive-history", headers=headers)
        assert history.status_code == 200, history.text
        event = next(row for row in history.json() if row["package_id"] == package_id)
        assert event["manifest_reference"] == "OA-MANIFEST-0001"
        assert event["actor"] == "retail-floor-operator"

        sale_payload = {
            "source_system": "OperatorAcceptancePOS",
            "import_batch_id": "OA-RETAIL-SALES-0001",
            "lines": [
                {
                    "source_record_id": "OA-SALE-0001",
                    "sold_at": "2026-08-31T16:00:00Z",
                    "quantity": 2,
                    "product_id": source["product_id"],
                    "sku": source["sku"],
                    "product_name": source["product_name"],
                    "net_sales": 60,
                }
            ],
        }
        sale = client.post("/api/v1/inventory/retail/sales/import", headers=headers, json=sale_payload)
        assert sale.status_code == 201, sale.text
        assert sale.json()["imported"] == 1
        sale_duplicate = client.post("/api/v1/inventory/retail/sales/import", headers=headers, json=sale_payload)
        assert sale_duplicate.status_code == 201, sale_duplicate.text
        assert sale_duplicate.json()["skipped_duplicates"] == 1

        audit = client.post(
            "/api/v1/inventory/retail/audits",
            headers=headers,
            json={
                "audit_number": "OA-RETAIL-AUDIT-0001",
                "scope_label": "Received operator-acceptance package",
                "notes": "Stateful audit acceptance",
                "lot_ids": [received_lot_id],
                "blind_count": False,
                "recount_tolerance": 0,
            },
        )
        assert audit.status_code == 201, audit.text
        audit_id = audit.json()["id"]

        detail = client.get(f"/api/v1/inventory/retail/audits/{audit_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert len(detail.json()["lines"]) == 1
        line = detail.json()["lines"][0]
        assert line["lot_id"] == received_lot_id
        assert line["expected_quantity"] == 12

        count = client.post(
            f"/api/v1/inventory/retail/audits/{audit_id}/counts",
            headers=headers,
            json={"counts": [{"line_id": line["id"], "counted_quantity": 12, "reason": "", "notes": "Physical count matched"}]},
        )
        assert count.status_code == 200, count.text
        assert count.json()["lines"][0]["variance_quantity"] == 0

        paused = client.post(f"/api/v1/inventory/retail/audits/{audit_id}/status", headers=headers, json={"status": "paused"})
        assert paused.status_code == 200, paused.text
        assert paused.json()["status"] == "paused"
        resumed = client.post(f"/api/v1/inventory/retail/audits/{audit_id}/status", headers=headers, json={"status": "in_progress"})
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == "in_progress"

        csv_report = client.get(f"/api/v1/inventory/retail/audits/{audit_id}/report.csv", headers=headers)
        xlsx_report = client.get(f"/api/v1/inventory/retail/audits/{audit_id}/report.xlsx", headers=headers)
        assert csv_report.status_code == 200
        assert "OA-RETAIL-LOT-0001" in csv_report.text
        assert xlsx_report.status_code == 200
        assert xlsx_report.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        completed = client.post(
            f"/api/v1/inventory/retail/audits/{audit_id}/complete",
            headers=headers,
            json={"post_adjustments": False},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"

        trends = client.get("/api/v1/retail-insights/trends?days=30", headers=headers)
        assert trends.status_code == 200, trends.text
    finally:
        app.dependency_overrides.clear()


def test_extraction_operator_can_plan_reserve_consume_hold_release_record_output_cost_and_qa():
    """Exercise the durable extraction workflow instead of treating Extraction as a dashboard."""

    client, headers = _seeded_client(role="dev", user_id="extraction-lead")
    try:
        workflows_response = client.get("/api/v1/extraction/workflows", headers=headers)
        lots_response = client.get("/api/v1/extraction/lots", headers=headers)
        products_response = client.get("/api/v1/extraction/products", headers=headers)
        assert workflows_response.status_code == 200, workflows_response.text
        assert lots_response.status_code == 200, lots_response.text
        assert products_response.status_code == 200, products_response.text

        workflows = workflows_response.json()
        workflow_by_key = {row["key"]: row for row in workflows}
        for required in ("bho_cured", "ethanol_crude", "dry_sift"):
            assert required in workflow_by_key, f"Extraction acceptance requires {required} to remain an available process."

        methods = {row["method"] for row in workflows}
        assert {"BHO", "Ethanol", "Solventless"}.issubset(methods)

        gram_products = [row for row in products_response.json() if str(row["base_unit"]).casefold() == "g"]
        assert gram_products, "Extraction acceptance requires at least one gram-based output product."
        output_product = gram_products[0]

        for index, workflow_key in enumerate(("bho_cured", "ethanol_crude", "dry_sift"), start=1):
            fresh_lots = client.get("/api/v1/extraction/lots", headers=headers)
            assert fresh_lots.status_code == 200, fresh_lots.text
            eligible = [row for row in fresh_lots.json() if row["available"] >= 2 and str(row["unit"]).casefold() == "g"]
            assert eligible, f"No gram-based extraction lot remained available for {workflow_key}."
            source = eligible[0]
            workflow = workflow_by_key[workflow_key]
            reserve_quantity = min(2.0, float(source["available"]))
            batch = f"OA-EXT-{index:02d}-{workflow_key.upper()}"

            created = client.post(
                "/api/v1/extraction/runs",
                headers=headers,
                json={
                    "batch_number": batch,
                    "workflow_key": workflow["key"],
                    "method": workflow["method"],
                    "product_family": workflow["label"],
                    "strain": "Operator Acceptance",
                    "operator": "extraction-lead",
                    "compliance_provider": "metrc",
                    "metrc_input_package_id": source["compliance_package_id"],
                    "notes": "Stateful extraction operator acceptance",
                },
            )
            assert created.status_code == 201, created.text
            run_id = created.json()["id"]
            assert created.json()["status"] in {"planned", "queued"}

            reserved = client.post(
                f"/api/v1/extraction/runs/{run_id}/inputs",
                headers=headers,
                json={
                    "lot_id": source["lot_id"],
                    "quantity": reserve_quantity,
                    "unit": source["unit"],
                    "role": "primary_input",
                    "source_reference": source["compliance_package_id"] or source["lot_code"],
                },
            )
            assert reserved.status_code == 201, reserved.text
            input_id = reserved.json()["id"]
            assert reserved.json()["status"] == "reserved"

            overconsume = client.post(
                f"/api/v1/extraction/inputs/{input_id}/consume",
                headers=headers,
                json={"quantity": reserve_quantity + 1, "reason": "Acceptance over-consume probe"},
            )
            assert overconsume.status_code == 422
            assert "exceeds" in overconsume.text.casefold()

            consume_quantity = reserve_quantity / 2
            consumed = client.post(
                f"/api/v1/extraction/inputs/{input_id}/consume",
                headers=headers,
                json={"quantity": consume_quantity, "reason": "Start operator acceptance extraction"},
            )
            assert consumed.status_code == 200, consumed.text
            assert consumed.json()["consumed_quantity"] == consume_quantity
            assert consumed.json()["status"] == "partial"

            first_stage = workflow["stages"][0]
            started = client.post(
                f"/api/v1/extraction/runs/{run_id}/events",
                headers=headers,
                json={
                    "stage_key": first_stage["key"],
                    "event_type": "started",
                    "input_weight_g": consume_quantity,
                    "operator": "extraction-lead",
                    "notes": "Operator began process",
                },
            )
            assert started.status_code == 201, started.text

            held = client.post(
                f"/api/v1/extraction/runs/{run_id}/events",
                headers=headers,
                json={"stage_key": first_stage["key"], "event_type": "hold", "notes": "Acceptance hold scenario"},
            )
            assert held.status_code == 201, held.text
            held_detail = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
            assert held_detail.status_code == 200, held_detail.text
            assert held_detail.json()["run"]["status"] == "hold"
            assert held_detail.json()["run"]["release_status"] == "blocked"

            released = client.post(
                f"/api/v1/extraction/runs/{run_id}/events",
                headers=headers,
                json={"stage_key": first_stage["key"], "event_type": "released", "notes": "Acceptance hold cleared"},
            )
            assert released.status_code == 201, released.text
            released_detail = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
            assert released_detail.status_code == 200, released_detail.text
            assert released_detail.json()["run"]["status"] == "active"

            output_quantity = consume_quantity / 2
            output = client.post(
                f"/api/v1/extraction/runs/{run_id}/outputs",
                headers=headers,
                json={
                    "product_id": output_product["id"],
                    "lot_code": f"{batch}-OUTPUT",
                    "quantity": output_quantity,
                    "output_label": f"{workflow['label']} operator-acceptance output",
                    "unit": "g",
                    "location_code": "WIP-EXTRACTION",
                    "notes": "Acceptance output",
                },
            )
            assert output.status_code == 201, output.text
            output_id = output.json()["id"]
            assert output.json()["status"] == "quarantine"

            cost = client.post(
                f"/api/v1/extraction/runs/{run_id}/costs",
                headers=headers,
                json={"category": "labor", "amount_usd": 12.5, "notes": "Operator acceptance labor"},
            )
            assert cost.status_code == 201, cost.text

            coa = client.post(
                f"/api/v1/extraction/runs/{run_id}/qa",
                headers=headers,
                json={
                    "event_type": "coa_attached",
                    "result": "passed",
                    "output_id": output_id,
                    "coa_reference": f"OA-COA-{index:02d}",
                    "notes": "Synthetic acceptance QA result",
                },
            )
            assert coa.status_code == 201, coa.text
            release = client.post(
                f"/api/v1/extraction/runs/{run_id}/qa",
                headers=headers,
                json={"event_type": "release", "result": "passed", "notes": "Acceptance QA release"},
            )
            assert release.status_code == 201, release.text

            final_detail = client.get(f"/api/v1/extraction/runs/{run_id}", headers=headers)
            assert final_detail.status_code == 200, final_detail.text
            snapshot = final_detail.json()
            assert snapshot["mass_balance"]["consumed_input"] == consume_quantity
            assert snapshot["mass_balance"]["recorded_output"] == output_quantity
            assert snapshot["mass_balance"]["yield_pct"] == 50
            assert any(row["coa_reference"] == f"OA-COA-{index:02d}" for row in snapshot["qa_events"])
            assert any(row["category"] == "labor" for row in snapshot["cost_events"])

            release_reservation = client.post(f"/api/v1/extraction/inputs/{input_id}/release", headers=headers)
            assert release_reservation.status_code == 200, release_reservation.text
            assert release_reservation.json()["reserved_quantity"] == consume_quantity

    finally:
        app.dependency_overrides.clear()


def test_extraction_floor_operator_cannot_self_approve_qa():
    client, headers = _seeded_client(role="operator", user_id="extraction-floor-operator")
    try:
        workflow = client.get("/api/v1/extraction/workflows", headers=headers).json()[0]
        created = client.post(
            "/api/v1/extraction/runs",
            headers=headers,
            json={
                "batch_number": "OA-EXT-ROLE-GATE",
                "workflow_key": workflow["key"],
                "method": workflow["method"],
                "product_family": workflow["label"],
                "operator": "extraction-floor-operator",
            },
        )
        assert created.status_code == 201, created.text
        denied = client.post(
            f"/api/v1/extraction/runs/{created.json()['id']}/qa",
            headers=headers,
            json={"event_type": "release", "result": "passed"},
        )
        assert denied.status_code == 403
        assert "cannot post extraction QA decisions" in denied.text
    finally:
        app.dependency_overrides.clear()
