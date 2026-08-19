"""Responsive, compatibility-safe navigation for the Buyer Dash shell.

The shell presents the simple business-language navigation approved for Buyer
Dash while continuing to route into the existing workspace/page identifiers.
Organization and facility selection remain owned by access_context.py.
"""

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
    # Match app.py's license gate exactly: missing feature flags default on,
    # while an explicit false removes Admin Tools from the flat shell too.
    from services.license_session import get_license_features

    features = get_license_features(state.get("license_session_data"))
    admin_exports_enabled = bool(features.get("admin_exports", True))
    return buyer_section_groups(
        is_admin=bool(state.get("is_admin", False)),
        user_role=str(state.get("auth_user_role") or "trial"),
        admin_exports_enabled=admin_exports_enabled,
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
            include = BUYER_WORKSPACE in workspaces and bool(
                flat_buyer_sections(category, dict(section_groups))
            )
        elif category == "Orders":
            include = COMMERCIAL_WORKSPACE in workspaces
        elif category == "Production":
            include = bool(
                workspaces.intersection(
                    {COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE}
                )
            )
        elif category == "Data & Settings":
            include = DATA_HUB_WORKSPACE in workspaces or bool(
                flat_buyer_sections(category, dict(section_groups))
            )
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
        workspace = next(
            (
                value
                for value in (COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE)
                if value in workspaces
            ),
            "",
        )
        if workspace:
            state["workspace_mode"] = workspace
            state["operations_group"] = (
                PRODUCTION_OPS if workspace != WHITE_LABEL_WORKSPACE else RETAIL_OPS
            )
        return
    if category == "Data & Settings":
        if DATA_HUB_WORKSPACE in workspaces:
            state["operations_group"] = DATA_OPERATIONS
            state["workspace_mode"] = DATA_HUB_WORKSPACE
            return
        sections = flat_buyer_sections(category, dict(section_groups))
        if sections:
            _set_buyer_route(state, sections[0], section_groups)


def _secondary_choices(
    category: str,
    groups: Mapping[str, Sequence[str]],
    section_groups: Mapping[str, Sequence[str]],
) -> list[tuple[str, str, str]]:
    """Return user-facing secondary choices for one flat category."""

    workspaces = _workspace_set(groups)
    if category in {"Inventory", "Purchasing", "Reports", "Compliance"}:
        return [
            (buyer_section_display_name(section), "section", section)
            for section in flat_buyer_sections(category, dict(section_groups))
        ]
    if category == "Production":
        display = {
            COMAN_WORKSPACE: "Co-Man Production",
            EXTRACTION_WORKSPACE: "Extraction",
            WHITE_LABEL_WORKSPACE: "White Label / Repack",
        }
        return [
            (display[workspace], "workspace", workspace)
            for workspace in (COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE)
            if workspace in workspaces
        ]
    if category == "Data & Settings":
        choices: list[tuple[str, str, str]] = []
        if DATA_HUB_WORKSPACE in workspaces:
            choices.append(("Imports & Data", "workspace", DATA_HUB_WORKSPACE))
        choices.extend(
            (buyer_section_display_name(section), "section", section)
            for section in flat_buyer_sections(category, dict(section_groups))
        )
        return choices
    return []


def _current_secondary_label(
    state: MutableMapping[str, Any],
    choices: Sequence[tuple[str, str, str]],
) -> str:
    current_workspace = str(state.get("workspace_mode") or "")
    current_section = str(state.get("buyer_section") or "")
    return next(
        (
            label
            for label, kind, value in choices
            if (kind == "workspace" and value == current_workspace)
            or (
                kind == "section"
                and value == current_section
                and current_workspace == BUYER_WORKSPACE
            )
        ),
        choices[0][0] if choices else "",
    )


def _apply_secondary_choice(
    state: MutableMapping[str, Any],
    selected_label: str,
    choices: Sequence[tuple[str, str, str]],
    section_groups: Mapping[str, Sequence[str]],
) -> None:
    selected = next((choice for choice in choices if choice[0] == selected_label), None)
    if not selected:
        return
    _, kind, value = selected
    if kind == "section":
        _set_buyer_route(state, value, section_groups)
        return
    state["workspace_mode"] = value
    if value == DATA_HUB_WORKSPACE:
        state["operations_group"] = DATA_OPERATIONS
    elif value == WHITE_LABEL_WORKSPACE:
        state["operations_group"] = RETAIL_OPS
    elif value in {COMAN_WORKSPACE, EXTRACTION_WORKSPACE}:
        state["operations_group"] = PRODUCTION_OPS


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


def _shell_css() -> str:
    """CSS for the approved dark/copper desktop shell and mobile layout."""

    return """
    <style>
    /* Old Buyer widgets remain available only in classic navigation mode. */
    .st-key-buyer_section_group, .st-key-buyer_section {display:none !important;}

    /* Desktop Option-B navigation. */
    .st-key-flat_navigation_section [role="radiogroup"] {
        display:flex !important;
        flex-direction:column !important;
        gap:.28rem !important;
    }
    .st-key-flat_navigation_section [role="radiogroup"] label {
        min-height:40px !important;
        margin:0 !important;
        padding:.48rem .62rem !important;
        border:1px solid transparent !important;
        border-radius:10px !important;
        background:transparent !important;
        transition:background .15s ease,border-color .15s ease,transform .15s ease !important;
    }
    .st-key-flat_navigation_section [role="radiogroup"] label:hover {
        background:rgba(255,255,255,.045) !important;
        border-color:rgba(255,255,255,.075) !important;
    }
    .st-key-flat_navigation_section [role="radiogroup"] label:has(input:checked) {
        background:linear-gradient(90deg,rgba(231,152,78,.18),rgba(231,152,78,.055)) !important;
        border-color:rgba(231,152,78,.34) !important;
        box-shadow:inset 3px 0 #E7984E !important;
    }
    .st-key-flat_navigation_section [role="radiogroup"] label:has(input:checked) p {
        color:#F4B36F !important;
        font-weight:780 !important;
    }
    .st-key-flat_nav_secondary [role="radiogroup"] {
        gap:.18rem !important;
    }
    .st-key-flat_nav_secondary [role="radiogroup"] label {
        min-height:34px !important;
        padding:.35rem .58rem !important;
        border-radius:9px !important;
    }
    .st-key-flat_nav_secondary [role="radiogroup"] label:has(input:checked) {
        background:rgba(231,152,78,.09) !important;
    }

    .dl-nav-context {
        margin:.15rem 0 .55rem;
        padding:.52rem .62rem;
        color:var(--dl-text-soft,#AAB4AC) !important;
        background:rgba(255,255,255,.025);
        border:1px solid rgba(255,255,255,.07);
        border-radius:10px;
        font-size:.72rem;
        line-height:1.35;
    }
    .dl-nav-context strong { color:var(--dl-text,#F5F7F4) !important; }

    /* Main-column mobile controls are intentionally absent from desktop. */
    .st-key-mobile_flat_navigation {display:none;}

    /* Approved global search bar. */
    .st-key-buyer_dash_global_search {
        position:relative;
        z-index:30;
        margin:0 0 1rem !important;
        padding:.2rem !important;
        border:1px solid rgba(255,255,255,.08);
        border-radius:15px;
        background:linear-gradient(145deg,rgba(24,28,25,.96),rgba(17,20,18,.92));
        box-shadow:0 12px 36px rgba(0,0,0,.20);
    }
    .st-key-buyer_dash_global_search [data-baseweb="input"] > div {
        min-height:48px !important;
        background:rgba(5,7,6,.55) !important;
        border-color:rgba(255,255,255,.10) !important;
        border-radius:12px !important;
    }
    .st-key-buyer_dash_global_search input {
        font-size:.95rem !important;
        padding-left:.3rem !important;
    }

    @media (max-width: 768px) {
        .block-container {
            width:100% !important;
            padding:.65rem .65rem 4.5rem !important;
        }
        .premium-commandbar {
            min-height:52px !important;
            margin-bottom:.55rem !important;
            padding:.5rem .58rem !important;
            border-radius:14px !important;
        }
        .premium-commandbar__context {display:none !important;}
        .premium-commandbar__mark {width:34px !important;height:34px !important;}

        .st-key-mobile_flat_navigation {
            display:block !important;
            margin:.2rem 0 .55rem !important;
            padding:.62rem !important;
            border:1px solid rgba(255,255,255,.09) !important;
            border-radius:14px !important;
            background:linear-gradient(145deg,rgba(24,28,25,.96),rgba(17,20,18,.94)) !important;
            box-shadow:0 10px 30px rgba(0,0,0,.20) !important;
        }
        .st-key-mobile_flat_navigation [data-testid="stCaptionContainer"] {
            margin-bottom:.25rem !important;
        }
        .st-key-buyer_dash_global_search {
            position:sticky !important;
            top:.35rem !important;
            z-index:999 !important;
            margin-bottom:.65rem !important;
            border-radius:13px !important;
        }
        .st-key-buyer_dash_global_search [data-baseweb="input"] > div {
            min-height:46px !important;
        }

        /* Streamlit columns are desktop-first. Wrap them into useful mobile cards. */
        div[data-testid="stHorizontalBlock"] {
            flex-wrap:wrap !important;
            gap:.55rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width:min(100%,220px) !important;
            flex:1 1 220px !important;
        }
        div[data-testid="stDataFrame"] {
            max-width:100% !important;
            overflow-x:auto !important;
        }
        .stButton > button, .stDownloadButton > button {
            min-height:44px !important;
        }
        h1 {font-size:clamp(1.75rem,9vw,2.35rem) !important;}
        h2 {font-size:clamp(1.35rem,7vw,1.8rem) !important;}
    }
    </style>
    """


def _render_secondary_sidebar(
    state: MutableMapping[str, Any],
    choices: Sequence[tuple[str, str, str]],
    section_groups: Mapping[str, Sequence[str]],
) -> None:
    import streamlit as st

    if not choices:
        return
    current_label = _current_secondary_label(state, choices)
    if state.get("flat_nav_tool_label") != current_label:
        state["flat_nav_tool_label"] = current_label

    def sync_secondary() -> None:
        _apply_secondary_choice(
            state,
            str(state.get("flat_nav_tool_label") or ""),
            choices,
            section_groups,
        )

    with st.container(key="flat_nav_secondary"):
        st.sidebar.radio(
            "Current area",
            [label for label, _, _ in choices],
            key="flat_nav_tool_label",
            on_change=sync_secondary,
            label_visibility="collapsed",
        )


def _render_data_mode_sidebar(state: MutableMapping[str, Any]) -> None:
    """Keep the old data-mode capability without cluttering primary nav."""
    import streamlit as st

    modes = ["📁 Uploads", "🔴 Dutchie Live"]
    current = str(state.get("data_mode") or modes[0])
    if current not in modes:
        current = modes[0]
        state["data_mode"] = current
    if state.get("flat_nav_data_mode") != current:
        state["flat_nav_data_mode"] = current

    def sync_data_mode() -> None:
        selected = str(state.get("flat_nav_data_mode") or modes[0])
        if selected in modes:
            state["data_mode"] = selected

    with st.sidebar.expander("Data source", expanded=False):
        st.selectbox(
            "Buyer data mode",
            modes,
            key="flat_nav_data_mode",
            on_change=sync_data_mode,
            label_visibility="collapsed",
        )


def _render_mobile_navigation(
    state: MutableMapping[str, Any],
    available: Sequence[str],
    groups: Mapping[str, Sequence[str]],
    section_groups: Mapping[str, Sequence[str]],
    category: str,
) -> None:
    import streamlit as st

    if state.get("mobile_flat_navigation_section") != category:
        state["mobile_flat_navigation_section"] = category

    def sync_mobile_category() -> None:
        selected = str(state.get("mobile_flat_navigation_section") or "")
        if selected in available:
            _default_route_for_category(state, selected, groups, section_groups)
            state["flat_navigation_section"] = selected
        state["workspace_navigation_revision"] = int(
            state.get("workspace_navigation_revision", 0)
        ) + 1

    with st.container(key="mobile_flat_navigation"):
        st.caption("BUYER DASH")
        st.selectbox(
            "Navigate",
            list(available),
            key="mobile_flat_navigation_section",
            on_change=sync_mobile_category,
            label_visibility="collapsed",
        )

        mobile_category = str(state.get("mobile_flat_navigation_section") or category)
        choices = _secondary_choices(mobile_category, groups, section_groups)
        if choices:
            current_label = _current_secondary_label(state, choices)
            if state.get("mobile_flat_nav_tool_label") != current_label:
                state["mobile_flat_nav_tool_label"] = current_label

            def sync_mobile_secondary() -> None:
                _apply_secondary_choice(
                    state,
                    str(state.get("mobile_flat_nav_tool_label") or ""),
                    choices,
                    section_groups,
                )

            st.selectbox(
                "Tool",
                [label for label, _, _ in choices],
                key="mobile_flat_nav_tool_label",
                on_change=sync_mobile_secondary,
                label_visibility="collapsed",
            )

        modes = ["📁 Uploads", "🔴 Dutchie Live"]
        current_mode = str(state.get("data_mode") or modes[0])
        if current_mode not in modes:
            current_mode = modes[0]
        if state.get("mobile_flat_nav_data_mode") != current_mode:
            state["mobile_flat_nav_data_mode"] = current_mode

        def sync_mobile_data_mode() -> None:
            selected = str(state.get("mobile_flat_nav_data_mode") or modes[0])
            if selected in modes:
                state["data_mode"] = selected
                state["flat_nav_data_mode"] = selected

        with st.expander("Data source", expanded=False):
            st.selectbox(
                "Buyer data mode",
                modes,
                key="mobile_flat_nav_data_mode",
                on_change=sync_mobile_data_mode,
                label_visibility="collapsed",
            )


def render_workspace_selector(
    groups: Mapping[str, Sequence[str]],
    *,
    preferred_group: str | None = None,
) -> tuple[str, str]:
    """Render the approved flat shell while preserving every legacy route."""

    import html
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

    st.markdown(_shell_css(), unsafe_allow_html=True)

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
    if state.get("flat_navigation_section") != inferred:
        state["flat_navigation_section"] = inferred

    def sync_flat_category() -> None:
        selected = str(state.get("flat_navigation_section") or "")
        if selected in available:
            _default_route_for_category(state, selected, groups, section_groups)
            state["mobile_flat_navigation_section"] = selected
        state["workspace_navigation_revision"] = int(
            state.get("workspace_navigation_revision", 0)
        ) + 1

    st.sidebar.markdown("### Buyer Dash")
    org_name = str(state.get("active_organization_name") or "")
    facility_name = str(state.get("active_facility_name") or "")
    context_text = " · ".join(value for value in [org_name, facility_name] if value)
    if context_text:
        st.sidebar.markdown(
            f'<div class="dl-nav-context"><strong>Active</strong><br>{html.escape(context_text)}</div>',
            unsafe_allow_html=True,
        )
    st.sidebar.caption("Choose the work, not the architecture.")
    category = st.sidebar.radio(
        "Navigate",
        available,
        key="flat_navigation_section",
        on_change=sync_flat_category,
        label_visibility="collapsed",
    )

    choices = _secondary_choices(category, groups, section_groups)
    _render_secondary_sidebar(state, choices, section_groups)
    _render_data_mode_sidebar(state)

    with st.sidebar.expander("Navigation options", expanded=False):
        st.toggle(
            "Use classic navigation",
            key="legacy_navigation_enabled",
            help="Compatibility fallback. No legacy pages are removed by the flat shell.",
        )

    _render_mobile_navigation(
        state,
        available,
        groups,
        section_groups,
        category,
    )

    # Search appears above the workspace content on every screen, as in the
    # approved hybrid concept.
    render_global_search(state)

    normalize_workspace_state(state, groups, preferred_group=preferred_group)
    return str(state["operations_group"]), str(state["workspace_mode"])
