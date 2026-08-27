from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cultivation_today_is_system_generated_and_forward_looking():
    source = read("frontend/src/components/CultivationToday.tsx")
    for marker in (
        "Cultivation Today",
        "What needs attention now",
        "Next Actions",
        "No separate task setup",
        "8-week harvest forecast",
        "Harvest next 7d",
        "Harvest next 30d",
        "Overdue harvest estimates",
        "Missing harvest estimates",
        "Unassigned rooms",
    ):
        assert marker in source


def test_cultivation_next_actions_open_existing_plant_360():
    inventory = read("frontend/src/components/PlantInventory.tsx")
    today = read("frontend/src/components/CultivationToday.tsx")
    assert 'import { WorkspaceWindow } from "./WorkspaceWindow"' in inventory
    assert '<CultivationToday plants={overview.data} onSelect={setSelected} />' in inventory
    assert "onClick={() => onSelect(item.plant)}" in today
    assert 'eyebrow="CULTIVATION · PLANT 360"' in inventory
    assert '<PlantDetail plant={selected}' in inventory
    assert "/transition" in inventory


def test_production_next_actions_are_generated_from_durable_run_state():
    source = read("frontend/src/components/ProductionNextActions.tsx")
    for marker in (
        'label: "Review QA hold"',
        'label: "Resolve material blocker"',
        'label: "Review held run"',
        'label: "Continue run execution"',
        'apiGet<QueueRow[]>("/api/v1/production/orders"',
        "Generated from Run 360 state",
    ):
        assert marker in source


def test_production_next_action_opens_exact_run_360():
    app = read("frontend/src/App.tsx")
    actions = read("frontend/src/components/ProductionNextActions.tsx")
    run360 = read("frontend/src/pages/ProductionRun360Page.tsx")
    assert "onOpenRun(action.row.order_id)" in actions
    assert "setRun360OrderId(orderId)" in app
    assert "<ProductionNextActions onOpenRun={openProductionRun360}" in app
    assert "initialOrderId={run360OrderId}" in app
    assert 'initialOrderId=""' in run360
    assert "if(initialOrderId)setSelected(initialOrderId)" in run360


def test_canix_roadmap_explicitly_rejects_separate_work_engine_destination():
    roadmap = read("docs/CANIX_COMPETITIVE_DISPLACEMENT.md")
    assert "There is no separate Work Engine destination." in roadmap
    assert "360 windows answer: Work on the thing." in roadmap
    assert "Next Actions" in roadmap
    assert "Production Run 360" in roadmap
    assert "Plant 360" in roadmap
    assert "Mobile/offline" in roadmap
    assert "Review & approvals" in roadmap
    assert "Native operational AI" in roadmap


def test_canix_displacement_scorecard_preserves_360_as_execution_surface():
    scorecard = read("docs/CANIX_DISPLACEMENT_SCORECARD.md")
    assert "Generated Next Actions attached to 360 objects; no separate task silo" in scorecard
    assert "Every action must execute through the existing durable 360/context" in scorecard
    assert "Production Next Actions -> Production Run 360" in scorecard
