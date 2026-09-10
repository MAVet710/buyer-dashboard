from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_doobie_agent_does_not_hit_ai_runtime_until_operator_opens_it():
    source = read("frontend/src/components/WorkspaceAgent.tsx")
    assert "enabled: open" in source
    assert "staleTime: 5 * 60_000" in source
    assert 'queryKey: ["workspace-ai-agents", operation, activePage]' in source


def test_stable_shell_identity_is_not_refetched_on_every_workspace_hop():
    source = read("frontend/src/main.tsx")
    assert 'client.setQueryDefaults(["account-context"]' in source
    assert 'client.setQueryDefaults(["access-options"]' in source
    assert source.count("staleTime: 5 * 60_000") >= 2
    assert "gcTime: 30 * 60_000" in source
