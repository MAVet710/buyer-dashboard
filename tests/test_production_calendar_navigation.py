from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_calendar_is_a_first_class_workspace_destination():
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    planning = (
        ROOT / "frontend" / "src" / "components" / "ProductionPlanningWorkspace.tsx"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "frontend" / "src" / "lib" / "workspaceRoutes.ts").read_text(encoding="utf-8")

    assert '{ label: "Calendar", page: "Production Calendar" }' in shell
    assert '"Production Calendar"' in shell
    assert 'page === "Production Calendar" ? <ProductionPlanningWorkspace onOpenRun={openProductionRun360} initialView="Calendar" />' in app
    assert 'page === "Production" ? <ProductionPlanningWorkspace onOpenRun={openProductionRun360} />' in app
    assert "<ProductionPlanner onOpenRun={onOpenRun} />" in planning
    assert "<ProductionCalendar onOpenRun={onOpenRun} />" in planning
    assert "<ProductionPage />" in planning
    assert '{ page: "Production Calendar", path: "/production/calendar" }' in routes
