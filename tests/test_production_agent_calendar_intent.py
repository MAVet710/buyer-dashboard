from __future__ import annotations

from services.agent_registry import PROFILES
from services.ai.action_tools import AgentActionRegistry, ProductionWeekActionPlanner
from services.ai.datasets import DatasetAccessContext


def _access() -> DatasetAccessContext:
    return DatasetAccessContext(
        organization_id="org-1",
        facility_id="facility-1",
        user_id="user-1",
        role="planner",
        capabilities=frozenset({"production"}),
        operation_type="production",
        engine=object(),
    )


def _resolve(question: str):
    registry = AgentActionRegistry(profile=PROFILES["coman"], access=_access(), question=question)
    return registry.deterministic_request()


def test_build_out_production_scheme_on_calendar_is_an_explicit_commit_request():
    resolved = _resolve("build out a production scheme on to our calendar in the app")
    assert resolved is not None
    name, arguments = resolved
    assert name == "production_schedule_week"
    assert arguments["commit"] is True
    assert arguments["days"] == 5
    assert arguments["max_runs"] == 12


def test_exact_request_executes_planner_with_commit_true(monkeypatch):
    question = "build out a production scheme on to our calendar in the app"
    registry = AgentActionRegistry(profile=PROFILES["coman"], access=_access(), question=question)
    resolved = registry.deterministic_request()
    assert resolved is not None
    name, arguments = resolved
    captured: dict[str, object] = {}

    def fake_plan(self, *, week_start, days, max_runs, commit, reason):
        captured.update(
            week_start=week_start,
            days=days,
            max_runs=max_runs,
            commit=commit,
            reason=reason,
        )
        return {
            "action": "production_schedule_week",
            "week_start": "2026-08-31",
            "week_end": "2026-09-04",
            "planned_count": 1,
            "committed_count": 1,
            "blocked_count": 0,
            "placements": [{"committed": True}],
            "mutation_performed": True,
        }

    monkeypatch.setattr(ProductionWeekActionPlanner, "plan", fake_plan)
    result = registry.execute(name, arguments)

    assert captured["commit"] is True
    assert captured["days"] == 5
    assert captured["max_runs"] == 12
    assert result["mutation_performed"] is True
    assert registry.mutation_performed is True


def test_create_production_schedule_on_calendar_is_an_explicit_commit_request():
    resolved = _resolve("create a production schedule on the calendar using what we have available")
    assert resolved is not None
    assert resolved[0] == "production_schedule_week"
    assert resolved[1]["commit"] is True


def test_schedule_production_on_calendar_is_an_explicit_commit_request_without_week_keyword():
    resolved = _resolve("schedule production on the calendar based on our current orders")
    assert resolved is not None
    assert resolved[0] == "production_schedule_week"
    assert resolved[1]["commit"] is True


def test_production_plan_preview_on_calendar_stays_read_only_without_mutation_language():
    resolved = _resolve("show me what a production plan could look like on the calendar based on available inventory")
    assert resolved is not None
    assert resolved[0] == "production_schedule_week"
    assert resolved[1]["commit"] is False


def test_plain_calendar_status_question_does_not_become_a_write_action():
    resolved = _resolve("what is currently on the production calendar")
    assert resolved is None


def test_generic_build_out_language_does_not_grant_calendar_write_permission():
    resolved = _resolve("build out production scheduling recommendations for me")
    assert resolved is None
