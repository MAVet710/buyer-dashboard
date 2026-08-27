from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cultivation_today_is_system_generated_and_forward_looking():
    source = read("frontend/src/components/CultivationToday.tsx")

    for marker in (
        "Cultivation Today",
        "What needs attention now",
        "Generated from live plant state. No task setup required.",
        "System-generated work queue",
        "8-week harvest forecast",
        "Harvest next 7d",
        "Harvest next 30d",
        "Overdue harvest estimates",
        "Missing harvest estimates",
        "Unassigned rooms",
    ):
        assert marker in source


def test_cultivation_today_generates_work_from_operational_state():
    source = read("frontend/src/components/CultivationToday.tsx")

    assert 'action: "Review harvest readiness"' in source
    assert 'action: "Prepare for harvest"' in source
    assert 'action: "Set harvest estimate"' in source
    assert 'action: "Assign cultivation room"' in source
    assert 'plant.phase === "flowering"' in source
    assert '["vegetative", "flowering"].includes(plant.phase)' in source
    assert 'plant.room_code === "UNASSIGNED"' in source


def test_generated_work_reuses_existing_plant_360_instead_of_parallel_mutations():
    inventory = read("frontend/src/components/PlantInventory.tsx")
    today = read("frontend/src/components/CultivationToday.tsx")

    assert 'import { CultivationToday } from "./CultivationToday"' in inventory
    assert '<CultivationToday plants={overview.data} onSelect={setSelected} />' in inventory
    assert "onClick={() => onSelect(item.plant)}" in today
    assert '<PlantDetail plant={selected}' in inventory
    assert "/transition" in inventory


def test_canix_displacement_roadmap_preserves_doobielogic_differentiators():
    roadmap = read("docs/CANIX_COMPETITIVE_DISPLACEMENT.md")

    for marker in (
        "Doobie Work Engine",
        "Mobile Operations Runtime",
        "offline action queue",
        "hardware abstraction layer",
        "Production Recipes/Templates",
        "Review & Approvals",
        "Native operational AI",
        "Extraction as a first-class operating workflow",
        "Purchasing intelligence",
        "fewer primary user decisions",
    ):
        assert marker in roadmap
