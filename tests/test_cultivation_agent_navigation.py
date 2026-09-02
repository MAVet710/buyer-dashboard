from pathlib import Path

from services.agent_registry import PROFILES, resolve_agent_profile


ROOT = Path(__file__).resolve().parents[1]


def test_cultivation_agent_is_registered_for_the_agent_directory():
    profile = PROFILES["cultivation"]
    assert profile.key == "cultivation"
    assert profile.name == "Cultivation Agent"
    assert "plant lifecycle and phase transitions" in profile.focus

    router = (ROOT / "backend" / "app" / "routers" / "ai_agents.py").read_text(encoding="utf-8")
    assert '"agents": [_profile_payload(profile) for profile in PROFILES.values()]' in router


def test_cultivation_ops_home_and_grow_workspace_select_cultivation_agent():
    assert resolve_agent_profile("Cultivation Ops", "Home").key == "cultivation"
    assert resolve_agent_profile("Cultivation Ops", "Cultivation").key == "cultivation"
    assert resolve_agent_profile("Cultivation Ops", "Grow Operations").key == "cultivation"
    assert resolve_agent_profile("Cultivation Ops", "Operations Control Tower").key == "cultivation"


def test_cultivation_mode_does_not_steal_compliance_workspaces():
    for page in ("Compliance", "Compliance Q&A", "Traceability Actions", "Label Studio"):
        assert resolve_agent_profile("Cultivation Ops", page).key == "compliance"


def test_retail_home_remains_operations_agent():
    assert resolve_agent_profile("Retail Ops", "Home").key == "ops"
