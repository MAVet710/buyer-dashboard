from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.observability import install_observability


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_planner_uses_one_bounded_snapshot_request() -> None:
    source = _read("frontend/src/components/ProductionPlanner.tsx")
    assert '/api/v1/production/planning-snapshot' in source
    assert '/api/v1/coman-parity/workspace' not in source
    assert "Promise.all(activeQueue.map" not in source
    assert "/api/v1/production/orders/${encodeURIComponent" not in source


def test_production_queue_read_model_does_not_call_order_360_in_a_loop() -> None:
    router = _read("backend/app/routers/production.py")
    read_model = _read("modules/production_erp/performance.py")
    assert "queue_summary_fast" in router
    assert "planning_snapshot" in router
    assert "order_360(" not in read_model


def test_production_calendar_uses_bounded_workspace_without_changing_scheduler_contract() -> None:
    page = _read("frontend/src/components/ProductionCalendar.tsx")
    router = _read("backend/app/routers/production_mutations.py")
    read_model = _read("modules/production_erp/calendar_read_model.py")

    assert '/api/v1/production/calendar-workspace' in page
    assert '/api/v1/coman-parity/workspace' not in page
    assert '/api/v1/production/schedule' in page
    assert '/schedule/preview' in page
    assert 'accept_warnings: acknowledged' in page
    assert '@production_router.get("/calendar-workspace")' in router
    assert "production_calendar_workspace" in router
    assert "ProductionOrder" in read_model
    assert "FacilityMachine" in read_model
    assert "MachineModel" in read_model
    assert "InventoryLot" not in read_model
    assert "InventoryTransaction" not in read_model
    assert "CrewAvailability" not in read_model


def test_run_360_uses_lightweight_product_options_not_coman_workspace() -> None:
    page = _read("frontend/src/pages/ProductionRun360Page.tsx")

    assert '/api/v1/inventory/products' in page
    assert 'queryKey:["inventory-products"]' in page
    assert '/api/v1/coman-parity/workspace' not in page
    assert '/api/v1/production/orders' in page
    assert '/mutations/preview' in page
    assert '/mutations/commit' in page


def test_label_studio_loads_lightweight_selector_then_selected_detail() -> None:
    page = _read("frontend/src/pages/LabelStudioPage.tsx")
    router = _read("backend/app/routers/label_printing.py")
    service = _read("backend/app/services/label_studio_fast.py")

    assert 'inventory-sources?summary=true' in page
    assert 'label-studio-inventory-source' in page
    assert '/inventory-sources/{lot_id}' in router
    assert "list_summaries" in service
    assert "resolve_for_lot" not in service.split("def list_summaries", 1)[1].split("def get_source", 1)[0]
    assert "_qr_svg" not in service.split("def list_summaries", 1)[1].split("def get_source", 1)[0]
    assert "_barcode_svg" not in service.split("def list_summaries", 1)[1].split("def get_source", 1)[0]


def test_product_master_list_batches_packaging_profiles() -> None:
    router = _read("backend/app/routers/product_master.py")
    list_body = router.split("def list_products", 1)[1].split("@router.post", 1)[0]

    assert "packaging_by_product" in list_body
    assert "ProductPackagingProfile.product_id.in_" in list_body
    assert "session.get(ProductPackagingProfile, row.id)" not in list_body


def test_retail_planning_batches_velocity_totals_without_per_product_sql() -> None:
    service = _read("modules/retail_planning/service.py")
    workspace = service.split("def workspace", 1)[1]

    assert "window_groups" in workspace
    assert "window_conditions" in workspace
    assert "sold_by_product" in workspace
    assert ".group_by(RetailSale.product_id)" in workspace
    assert "RetailSale.product_id == product.id" not in workspace


def test_performance_contract_is_part_of_engineering_requirements() -> None:
    plan = _read("PLAN.md")
    agents = _read("AGENTS.md")
    implement = _read("IMPLEMENT.md")
    contract = _read("docs/PERFORMANCE_CONTRACT.md")

    assert "PERFORMANCE_CONTRACT.md" in plan
    assert "simple and fast on top" in plan
    assert "React frontend + FastAPI backend" in agents
    assert "per-row HTTP" in agents
    assert "PERFORMANCE_CONTRACT.md" in implement
    assert "No per-row HTTP fan-out" in contract
    assert "No per-row SQL fan-out" in contract


def test_api_exposes_server_timing_without_changing_payload() -> None:
    app = FastAPI()
    install_observability(app)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    response = TestClient(app).get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["server-timing"].startswith("app;dur=")
    assert float(response.headers["x-response-time-ms"]) >= 0
    assert response.headers["x-request-id"]
