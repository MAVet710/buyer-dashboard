from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_plan_is_decision_first_and_opens_existing_run_360():
    app = read("frontend/src/App.tsx")
    planner = read("frontend/src/components/ProductionPlanner.tsx")

    assert 'import { ProductionPlanner } from "./components/ProductionPlanner"' in app
    assert "<ProductionPlanner onOpenRun={openProductionRun360}" in app
    assert "What should we run next?" in planner
    assert 'type Decision = "CONTINUE" | "RUN NOW" | "RUN NEXT" | "AT RISK" | "BLOCKED"' in planner
    assert "onClick={() => onOpenRun(row.orderId)}" in planner
    assert 'apiGet<QueueRow[]>("/api/v1/production/orders", signal)' in planner
    assert "/api/v1/production/orders/${encodeURIComponent(row.order_id)}" in planner


def test_production_plan_uses_material_labor_machine_and_standard_signals():
    planner = read("frontend/src/components/ProductionPlanner.tsx")

    assert "materialReadiness(detail" in planner
    assert "reservedByLot" in planner
    assert "lot.on_hand" in planner
    assert "expected_labor_hours" in planner
    assert "available_people" in planner
    assert "machineCategories" in planner
    assert "resource_category" in planner
    assert "standard_configured" in planner
    assert "QA hold requires review" in planner
    assert "compliance_checkpoint" in planner


def test_production_shortage_can_never_auto_purchase():
    planner = read("frontend/src/components/ProductionPlanner.tsx")
    roadmap = read("docs/CANIX_DISPLACEMENT_IMPLEMENTATION.md")

    assert "Purchasing remains human-controlled" in planner
    assert "Buyer review" in planner
    assert "apiPost(" not in planner
    assert "automatically create, submit, approve, or place a purchase order" in roadmap
    assert "a human buyer retains control" in roadmap
    assert "The plan never performs a purchasing mutation." in roadmap
