from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from services.agent_registry import PROFILES
from services.ai.action_tools import AgentActionRegistry, ProductionWeekActionPlanner
from services.ai.datasets import DatasetAccessContext
from services.ai.schemas import AgentResult


ROOT = Path(__file__).resolve().parents[1]


def _access(*, role: str = "planner", capabilities: frozenset[str] = frozenset({"production"}), engine=object()):
    return DatasetAccessContext(
        organization_id="org-1",
        facility_id="facility-1",
        user_id="user-1",
        role=role,
        capabilities=capabilities,
        operation_type="production",
        engine=engine,
    )


def test_coman_agent_exposes_governed_week_scheduler_only_to_authorized_production_roles():
    authorized = AgentActionRegistry(
        profile=PROFILES["coman"],
        access=_access(role="planner"),
        question="map out a week of production on the calendar with available inventory",
    )
    assert "production_schedule_week" in authorized.names()

    operator = AgentActionRegistry(
        profile=PROFILES["coman"],
        access=_access(role="operator"),
        question="map out a week of production on the calendar with available inventory",
    )
    assert operator.names() == ()

    retail_only = AgentActionRegistry(
        profile=PROFILES["coman"],
        access=_access(capabilities=frozenset({"retail"})),
        question="map out a week of production on the calendar with available inventory",
    )
    assert retail_only.names() == ()


def test_exact_user_request_resolves_to_deterministic_calendar_action_and_explicit_commit():
    actions = AgentActionRegistry(
        profile=PROFILES["coman"],
        access=_access(),
        question="can you map out a week of production on the calendar with available inventory",
    )
    resolved = actions.deterministic_request()
    assert resolved is not None
    name, arguments = resolved
    assert name == "production_schedule_week"
    assert arguments["commit"] is True
    assert arguments["days"] == 5


def test_schedule_preview_language_does_not_become_mutation_permission_and_honors_next_week():
    actions = AgentActionRegistry(
        profile=PROFILES["coman"],
        access=_access(),
        question="show me what next week's production schedule could look like on the calendar",
    )
    resolved = actions.deterministic_request()
    assert resolved is not None
    assert resolved[0] == "production_schedule_week"
    assert resolved[1]["commit"] is False
    assert resolved[1]["week_start"] == "next_week"


def test_model_cannot_force_commit_when_user_only_requested_preview():
    actions = AgentActionRegistry(
        profile=PROFILES["coman"],
        access=_access(),
        question="show me what next week's production schedule could look like on the calendar",
    )
    result = actions.execute("production_schedule_week", {"commit": True})
    assert result["error"] == "confirmation_required"
    assert result["mutation_performed"] is False
    assert actions.mutation_performed is False


def test_agent_result_preserves_action_state_in_api_payload():
    result = AgentResult(
        answer="I scheduled two safe runs.",
        provider="deterministic",
        model="python/sql",
        read_only=False,
        action_results=[{"action": "production_schedule_week", "committed_count": 2, "mutation_performed": True}],
    ).as_dict()
    assert result["read_only"] is False
    assert result["action_results"][0]["committed_count"] == 2


def test_week_planner_never_auto_accepts_warnings_or_buys_material():
    source = (ROOT / "services" / "ai" / "action_tools.py").read_text(encoding="utf-8")
    assert 'accept_warnings=False' in source
    assert 'blocker_count' in source
    assert "ProductionScheduleService" in source
    assert "create_purchase_order" not in source


def test_unreserved_available_material_requires_human_work_location_before_reservation_or_metrc_move():
    source = (ROOT / "services" / "ai" / "action_tools.py").read_text(encoding="utf-8")
    assert 'MATERIAL_STAGING_WARNING = "material_unreserved"' in source
    assert '"required_input": "destination_work_location"' in source
    assert '"staging_lots": self._staging_lots(snapshot)' in source
    assert "never reserves them" in source
    assert "Metrc package move" in source
    assert "reserve_bom_materials(" not in source
    assert "package_move" in source


def test_staging_policy_keeps_material_dependent_runs_uncommitted_until_human_input():
    source = (ROOT / "services" / "ai" / "action_tools.py").read_text(encoding="utf-8")
    assert 'if row["requires_human_input"]:' in source
    assert "continue" in source
    assert "destination work location" in source
    assert "provider readback" in source


def test_held_runs_are_excluded_from_automatic_candidate_selection_contract():
    source = (ROOT / "services" / "ai" / "action_tools.py").read_text(encoding="utf-8")
    assert 'HELD_STATUSES = {"on_hold", "hold", "held"}' in source
    assert "status in CLOSED_STATUSES or status in HELD_STATUSES" in source


def test_next_week_token_resolves_to_following_monday():
    assert ProductionWeekActionPlanner._next_week_start(date(2026, 8, 30)) == date(2026, 8, 31)
    assert ProductionWeekActionPlanner._next_week_start(date(2026, 8, 31)) == date(2026, 9, 7)
    resolved = ProductionWeekActionPlanner._resolve_start_day(
        "next_week",
        ZoneInfo("America/New_York"),
        today=date(2026, 8, 30),
    )
    assert resolved == date(2026, 8, 31)


def test_same_day_slot_rounding_always_moves_into_the_future():
    tz = ZoneInfo("America/New_York")
    value = datetime(2026, 8, 31, 10, 12, 17, tzinfo=tz)
    rounded = ProductionWeekActionPlanner._ceil_to_half_hour(value)
    assert rounded > value
    assert rounded.hour == 10
    assert rounded.minute == 30

    half_hour = datetime(2026, 8, 31, 10, 30, 0, tzinfo=tz)
    rounded_half = ProductionWeekActionPlanner._ceil_to_half_hour(half_hour)
    assert rounded_half > half_hour
    assert rounded_half.hour == 11
    assert rounded_half.minute == 0


def test_workspace_agent_surfaces_governed_actions_instead_of_permanent_read_only_badge():
    source = (ROOT / "frontend" / "src" / "components" / "WorkspaceAgent.tsx").read_text(encoding="utf-8")
    assert "Operational actions" in source
    assert "Action applied" in source
    assert "action_results" in source
    assert "Eligible actions are server-scoped" in source
    assert '<span className="read-only-chip">Read-only</span>' not in source


def test_action_prompt_keeps_read_tools_read_only_and_blocks_warning_bypass():
    source = (ROOT / "services" / "ai" / "context.py").read_text(encoding="utf-8")
    assert "Authorized operational action tools" in source
    assert "Read-only tools remain read-only" in source
    assert "auto-accept warnings/blockers" in source
    assert "explicitly asks you to perform that exact operational change" in source


def test_business_day_helper_skips_weekends():
    days = ProductionWeekActionPlanner._business_days(date(2026, 8, 28), 3)
    assert [value.isoformat() for value in days] == ["2026-08-28", "2026-08-31", "2026-09-01"]
