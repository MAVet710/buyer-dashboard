from __future__ import annotations

from services.agent_registry import PROFILES
from services.ai.action_tools import AgentActionRegistry
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
