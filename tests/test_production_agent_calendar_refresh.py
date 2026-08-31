from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_agent_refreshes_production_calendar_after_applied_schedule_action():
    source = (ROOT / "frontend" / "src" / "components" / "WorkspaceAgent.tsx").read_text(encoding="utf-8")
    assert "useQueryClient" in source
    assert "productionCalendarChanged" in source
    assert "action.mutation_performed" in source
    assert 'action.action === "production_schedule_week"' in source
    assert 'action.tool === "production_schedule_week"' in source
    assert 'invalidateQueries({ queryKey: ["production-calendar"] })' in source
    assert 'invalidateQueries({ queryKey: ["production-calendar-workspace"] })' in source
    assert 'invalidateQueries({ queryKey: ["production-calendar-order"] })' in source
