from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_calendar_is_a_first_class_workspace_destination():
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    routes = (ROOT / "frontend" / "src" / "lib" / "workspaceRoutes.ts").read_text(encoding="utf-8")

    assert '{ label: "Calendar", page: "Production Calendar" }' in shell
    assert '"Production Calendar"' in shell
    assert 'page === "Production Calendar" ? <ProductionCalendar onOpenRun={openProductionRun360}/>' in app
    assert 'page === "Production" ? <><ProductionPlanner onOpenRun={openProductionRun360}/><ProductionNextActions onOpenRun={openProductionRun360}/><ProductionPage /></>' in app
    assert '{ page: "Production Calendar", path: "/production/calendar" }' in routes
