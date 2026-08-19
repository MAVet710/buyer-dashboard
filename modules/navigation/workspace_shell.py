"""Reliable, compatibility-safe navigation for the Streamlit shell."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    FLAT_NAV_ORDER,
    HOME_OPS,
    HOME_WORKSPACE,
    PRODUCTION_OPS,
    RETAIL_OPS,
    WHITE_LABEL_WORKSPACE,
    buyer_section_display_name,
    buyer_section_groups,
    flat_buyer_sections,
    flat_category_for_route,
)


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


def _workspace_set(groups: Mapping[str, Sequence[str]]) -> set[str]:
    return {workspace for options in groups.values() for workspace in options}


def _buyer_groups_for_state(state: MutableMapping[str, Any]) -> dict[str, list[str]]:
    return buyer_section_groups(
        is_admin=bool(state.get("is_admin", False)),
        user_role=str(state.get("auth_user_role") or "trial"),
        admin_exports_enabled=True,
    )


def _buyer_group_for_section(section_groups: Mapping[str, Sequence[str]], section: str) -> str:
    return next(
        (group for group, sections in section_groups.items() if section in sections),
        next(iter(section_groups), "Overview"),
    )


def _set_buyer_route(
    state: MutableMapping[str, Any],
    section: str,
    section_groups: Mapping[str, Sequence[str]],
) -> None:
    state["operations_group"] = RETAIL_OPS
    state["workspace_mode"] = BUYER_WORKSPACE
    state["buyer_section"] = section
    state["buyer_section_group"] = _buyer_group_for_section(section_groups, section)


def _available_flat_categories(
    groups: Mapping[str, Sequence[str]],
    section_groups: Mapping[str, Sequence[str]],
) -> list[str]:
    workspaces = _workspace_set(groups)
    available: list[str] = []
    for category in FLAT_NAV_ORDER:
        include = False
        if category == "Home":
            include = HOME_WORKSPACE in workspaces
        elif category in {"Inventory", "Purchasing", "Reports", "Compliance"}:
            include = BUYER_WORKSPACE in workspaces and bool(flat_buyer_sections(category, dict(section_groups)))
        elif category == "Orders":
            include = COMMERCIAL_WORKSPACE in workspaces
        elif category == "Production":
            include = bool(workspaces.intersection({COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE}))
        elif category == "Data & Settings":
            include = DATA_HUB_WORKSPACE in workspaces or bool(flat_buyer_sections(category, dict(section_groups)))
        if include:
            available.append(category)
    return available


def _default_route_for_category(
    state: MutableMapping[str, Any],
    category: str,
    groups: Mapping[str, Sequence[str]],
    section_groups: Mapping[str, Sequence[str]],
) -> None:
    workspaces = _workspace_set(groups)
    if category == "Home" and HOME_WORKSPACE in workspaces:
        state["operations_group"] = HOME_OPS
        state["workspace_mode"] = HOME_WORKSPACE
        return
    if category in {"Inventory", "Purchasing", "Reports", "Compliance"} and BUYER_WORKSPACE in workspaces:
        sections = flat_buyer_sections(category, dict(section_groups))
        preferred = {
            "Inventory": "📊 Inventory Dashboard",
            "Purchasing": "🧾 PO Builder",
            "Reports": "📈 Trends",
            "Compliance": "🧭 Compliance Q&A",
        }.get(category, "")
        section = preferred if preferred in sections else (sections[0] if sections else "")
        if section:
            _set_buyer_route(state, section, section_groups)
        return
    if category == "Orders" and COMMERCIAL_WORKSPACE in workspaces:
        state["operations_group"] = COMMERCIAL_OPS
        state["workspace_mode"] = COMMERCIAL_WORKSPACE
        return
    if category == "Production":
        preferred = [COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE]
        workspace = next((value for value in preferred if value in workspaces), "")
        if workspace:
            state["workspace_mode"] = workspace
            state["operations_group"] = PRODUCTION_OPS if workspace != WHITE_LABEL_WORKSPACE else RETAIL_OPS
        return
    if category == "Data & Settings":
        if DATA_HUB_WORKSPACE in workspaces:
            state["operations_group"] = DATA_OPERATIONS
            state["workspace_mode"] = DATA_HUB_WORKSPACE
            return
        sections = flat_buyer_sections(category, dict(section_groups))
        if sections:
            _set_buyer_route(state, sections[0], section_groups)


def _render_legacy_selector(
    groups: Mapping[str, Sequence[str]],
    *,
    preferred_group: str | None = None,
) -> tuple[str, str]:
    import streamlit as st

    normalize_workspace_state(st.session_state, groups, preferred_group=preferred_group)

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


def _render_flat_secondary(
    groups: Mapping[str, Sequence[str]],
    category: str,
    section_groups: Mapping[str, Sequence[str]],
) -> None:
    import streamlit as st

    workspaces = _workspace_set(groups)
    state = st.session_state

    if category in {"Inventory", "Purchasing", "Reports", "Compliance"}:
        sections = flat_buyer_sections(category, dict(section_groups))
        if not sections:
            return
        current = str(state.get("buyer_section") or "")
        if current not in sections:
            current = sections[0]
            _set_buyer_route(state, current, section_groups)
        state["flat_nav_tool"] = current

        def sync_buyer_tool() -> None:
            selected = str(state.get("flat_nav_tool") or "")
            if selected in sections:
                _set_buyer_route(state, selected, section_groups)

        st.sidebar.radio(
            "Tools",
            sections,
            key="flat_nav_tool",
            format_func=buyer_section_display_name,
            on_change=sync_buyer_tool,
            label_visibility="collapsed",
        )
        return

    if category == "Production":
        options = [
            workspace
            for workspace in (COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE)
            if workspace in workspaces
        ]
        if not options:
            return
        current = str(state.get("workspace_mode") or "")
        if current not in options:
            current = options[0]
            state["workspace_mode"] = current
            state["operations_group"] = PRODUCTION_OPS if current != WHITE_LABEL_WORKSPACE else RETAIL_OPS
        state["flat_nav_production_tool"] = current
        display = {
            COMAN_WORKSPACE: "Co-Man Production",
            EXTRACTION_WORKSPACE: "Extraction",
            WHITE_LABEL_WORKSPACE: "White Label / Repack",
        }

        def sync_production_tool() -> None:
            selected = str(state.get("flat_nav_production_tool") or "")
            if selected in options:
                state["workspace_mode"] = selected
                state["operations_group"] = PRODUCTION_OPS if selected != WHITE_LABEL_WORKSPACE else RETAIL_OPS

        st.sidebar.radio(
            "Production tools",
            options,
            key="flat_nav_production_tool",
            format_func=lambda value: display.get(value, value),
            on_change=sync_production_tool,
            label_visibility="collapsed",
        )
        return

    if category == "Data & Settings":
        choices: list[tuple[str, str, str]] = []
        if DATA_HUB_WORKSPACE in workspaces:
            choices.append(("Imports & Data", "workspace", DATA_HUB_WORKSPACE))
        for section in flat_buyer_sections(category, dict(section_groups)):
            choices.append((buyer_section_display_name(section), "section", section))
        if not choices:
            return
        current_workspace = str(state.get("workspace_mode") or "")
        current_section = str(state.get("buyer_section") or "")
        current_label = next(
            (
                label
                for label, kind, value in choices
                if (kind == "workspace" and value == current_workspace)
                or (kind == "section" and value == current_section and current_workspace == BUYER_WORKSPACE)
            ),
            choices[0][0],
        )
        labels = [label for label, _, _ in choices]
        state["flat_nav_data_tool"] = current_label

        def sync_data_tool() -> None:
            selected_label = str(state.get("flat_nav_data_tool") or "")
            selected = next((row for row in choices if row[0] == selected_label), choices[0])
            _, kind, value = selected
            if kind == "workspace":
                state["operations_group"] = DATA_OPERATIONS
                state["workspace_mode"] = value
            else:
                _set_buyer_route(state, value, section_groups)

        st.sidebar.radio(
            "Data and settings tools",
            labels,
            key="flat_nav_data_tool",
            on_change=sync_data_tool,
            label_visibility="collapsed",
        )


def render_workspace_selector(
    groups: Mapping[str, Sequence[str]],
    *,
    preferred_group: str | None = None,
) -> tuple[str, str]:
    """Render flat task navigation while preserving the legacy route contract.

    Organization and facility selection remain owned by render_access_context,
    which renders above this shell in the sidebar. The flat shell never mutates
    active_organization_id or active_facility_id.
    """

    import streamlit as st
    from modules.navigation.product_360 import render_global_search

    normalize_workspace_state(st.session_state, groups, preferred_group=preferred_group)
    state = st.session_state
    state.setdefault("legacy_navigation_enabled", False)
    state["flat_navigation_enabled"] = not bool(state.get("legacy_navigation_enabled"))

    if state.get("legacy_navigation_enabled"):
        result = _render_legacy_selector(groups, preferred_group=preferred_group)
        with st.sidebar.expander("Navigation options", expanded=False):
            st.toggle("Use classic navigation", key="legacy_navigation_enabled")
        return result

    # app.py still owns the legacy Buyer Retail Area/Tool widgets. Hide those
    # two controls only while the flat shell is active; classic-navigation mode
    # leaves them untouched. No page or route is removed.
    st.markdown(
        """
        <style>
        .st-key-buyer_section_group, .st-key-buyer_section {display:none !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    section_groups = _buyer_groups_for_state(state)
    available = _available_flat_categories(groups, section_groups)
    if not available:
        return _render_legacy_selector(groups, preferred_group=preferred_group)

    inferred = flat_category_for_route(
        str(state.get("workspace_mode") or ""),
        str(state.get("buyer_section") or ""),
    )
    if inferred not in available:
        inferred = available[0]
    state["flat_navigation_section"] = inferred

    def sync_flat_category() -> None:
        selected = str(state.get("flat_navigation_section") or "")
        if selected in available:
            _default_route_for_category(state, selected, groups, section_groups)
        state["workspace_navigation_revision"] = int(state.get("workspace_navigation_revision", 0)) + 1

    # Access Context (Organization + Facility) is intentionally rendered by
    # app.py immediately before this block, so the tenant switcher stays fixed
    # above the simplified navigation.
    st.sidebar.markdown("### Buyer Dash")
    if state.get("active_facility_name"):
        st.sidebar.caption(f"Active facility: {state.get('active_facility_name')}")
    st.sidebar.caption("Choose the work, not the architecture.")
    category = st.sidebar.radio(
        "Navigate",
        available,
        key="flat_navigation_section",
        on_change=sync_flat_category,
        label_visibility="collapsed",
    )
    _render_flat_secondary(groups, category, section_groups)

    with st.sidebar.expander("Navigation options", expanded=False):
        st.toggle(
            "Use classic navigation",
            key="legacy_navigation_enabled",
            help="Temporary compatibility fallback. No legacy pages are removed by the flat shell.",
        )

    # Search is intentionally rendered before expensive workspace content so a
    # user can jump directly to a product or task from anywhere in the app.
    render_global_search(state)

    normalize_workspace_state(state, groups, preferred_group=preferred_group)
    return str(state["operations_group"]), str(state["workspace_mode"])
