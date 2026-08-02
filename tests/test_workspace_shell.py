from modules.navigation.workspace_shell import normalize_workspace_state


GROUPS = {
    "Retail Ops": ["Buyer", "Repack"],
    "Production Ops": ["Co-Man", "Extraction"],
}


def test_workspace_state_defaults_to_preferred_group() -> None:
    state = {}

    group, workspace = normalize_workspace_state(
        state,
        GROUPS,
        preferred_group="Production Ops",
    )

    assert (group, workspace) == ("Production Ops", "Co-Man")


def test_workspace_state_repairs_mismatched_saved_workspace() -> None:
    state = {"operations_group": "Retail Ops", "workspace_mode": "Extraction"}

    group, workspace = normalize_workspace_state(state, GROUPS)

    assert (group, workspace) == ("Retail Ops", "Buyer")


def test_workspace_state_preserves_valid_selection() -> None:
    state = {"operations_group": "Production Ops", "workspace_mode": "Extraction"}

    group, workspace = normalize_workspace_state(state, GROUPS)

    assert (group, workspace) == ("Production Ops", "Extraction")
