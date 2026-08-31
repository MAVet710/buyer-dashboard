from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_agent_refreshes_production_calendar_after_applied_action():
    source = (ROOT / "frontend" / "src" / "components" / "WorkspaceAgent.tsx").read_text(encoding="utf-8")
    assert "useQueryClient" in source
    assert "action.mutation_performed" in source
    assert 'invalidateQueries({ queryKey: ["production-calendar"] })' in source
    assert 'invalidateQueries({ queryKey: ["production-calendar-workspace"] })' in source
    assert 'invalidateQueries({ queryKey: ["production-calendar-order"] })' in source
