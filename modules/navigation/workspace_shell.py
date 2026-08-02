"""Reliable, task-first workspace navigation for the Streamlit shell."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any


def normalize_workspace_state(
    state: MutableMapping[str, Any],
    groups: Mapping[str, Sequence[str]],
    *,
    preferred_group: str | None = None,
) -> tuple[str, str]:
    """Keep the selected operations group and workspace mutually consistent."""

    available_groups = [name for name, options in groups.items() if options]
    if not available_groups:
        raise ValueError("At least one workspace group is required.")

    selected_group = str(state.get("operations_group") or "")
    if selected_group not in available_groups:
        selected_group = (
            preferred_group if preferred_group in available_groups else available_groups[0]
        )
        state["operations_group"] = selected_group

    group_options = list(groups[selected_group])
    selected_workspace = str(state.get("workspace_mode") or "")
    if selected_workspace not in group_options:
        selected_workspace = group_options[0]
        state["workspace_mode"] = selected_workspace
    return selected_group, selected_workspace


def render_workspace_selector(
    groups: Mapping[str, Sequence[str]],
    *,
    preferred_group: str | None = None,
) -> tuple[str, str]:
    """Render a pointer-safe workspace selector before expensive page work."""

    import streamlit as st

    normalize_workspace_state(
        st.session_state,
        groups,
        preferred_group=preferred_group,
    )

    def sync_group() -> None:
        selected_group = st.session_state.get("operations_group")
        options = list(groups.get(selected_group, ()))
        if options and st.session_state.get("workspace_mode") not in options:
            st.session_state["workspace_mode"] = options[0]
        st.session_state["workspace_navigation_revision"] = int(
            st.session_state.get("workspace_navigation_revision", 0)
        ) + 1

    def mark_workspace_change() -> None:
        st.session_state["workspace_navigation_revision"] = int(
            st.session_state.get("workspace_navigation_revision", 0)
        ) + 1

    with st.container(key="workspace_navigator"):
        group_col, workspace_col = st.columns([1, 1.65])
        with group_col:
            operation_group = st.selectbox(
                "Operations Area",
                list(groups),
                help=(
                    "Retail Ops contains buying and repack tools. Production Ops contains "
                    "Co-Man and extraction tools. Data & Integrations loads shared operational sources."
                ),
                key="operations_group",
                on_change=sync_group,
            )
        workspace_options = list(groups[operation_group])
        if st.session_state.get("workspace_mode") not in workspace_options:
            st.session_state["workspace_mode"] = workspace_options[0]
        with workspace_col:
            workspace = st.selectbox(
                "Workspace",
                workspace_options,
                help=f"Choose a workspace inside {operation_group}.",
                key="workspace_mode",
                on_change=mark_workspace_change,
            )
    return operation_group, workspace
