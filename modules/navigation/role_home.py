"""Role-aware operating home for fast, guided task entry."""

from __future__ import annotations

from dataclasses import dataclass
import html
from typing import Any, MutableMapping

import streamlit as st

from modules.data_hub import build_data_hub_status
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    PRODUCTION_OPS,
    RETAIL_OPS,
    queue_workspace_navigation,
)


@dataclass(frozen=True)
class HomeAction:
    label: str
    description: str
    group: str
    workspace: str
    section: str = ""
    roles: tuple[str, ...] = ()


HOME_ACTIONS = (
    HomeAction("Review inventory", "See stock health, reorders, and aging risk.", RETAIL_OPS, BUYER_WORKSPACE, "📊 Inventory Dashboard", ("dev", "admin", "buyer", "read_only")),
    HomeAction("Start an inventory audit", "Scan labels and reconcile a durable count session.", RETAIL_OPS, BUYER_WORKSPACE, "📋 Inventory Counts", ("dev", "admin", "buyer", "supervisor", "operator", "qa")),
    HomeAction("Build purchasing decisions", "Review deliveries, budgets, and purchase orders.", RETAIL_OPS, BUYER_WORKSPACE, "🧾 PO Builder", ("dev", "admin", "buyer")),
    HomeAction("Plan Co-Man production", "Balance orders, machines, crews, and hand labor.", PRODUCTION_OPS, COMAN_WORKSPACE, roles=("dev", "admin", "planner", "supervisor", "operator", "qa")),
    HomeAction("Review extraction", "Inspect run performance, yields, and production risks.", PRODUCTION_OPS, EXTRACTION_WORKSPACE, roles=("dev", "admin", "planner", "supervisor", "operator", "qa")),
    HomeAction("Manage orders", "Track customer orders and fulfillment readiness.", COMMERCIAL_OPS, COMMERCIAL_WORKSPACE, roles=("dev", "admin", "buyer", "planner", "supervisor")),
    HomeAction("Import operational data", "Load, validate, and reuse files across workspaces.", DATA_OPERATIONS, DATA_HUB_WORKSPACE),
)


def actions_for_role(role: str) -> tuple[HomeAction, ...]:
    normalized = str(role or "trial").strip().lower()
    return tuple(
        action for action in HOME_ACTIONS if not action.roles or normalized in action.roles
    )


def activate_home_action(state: MutableMapping[str, Any], action: HomeAction) -> None:
    queue_workspace_navigation(
        state,
        group=action.group,
        workspace=action.workspace,
        buyer_section=action.section,
    )


def render_role_home(
    *,
    user_name: str,
    role: str,
    organization_name: str = "",
    facility_name: str = "",
    ai_connected: bool = False,
) -> None:
    """Render a concise role-specific landing page and task launcher."""

    normalized_role = str(role or "trial").strip().lower()
    safe_name = html.escape(str(user_name or "Operator"))
    role_label = normalized_role.replace("_", " ").title()
    context = " · ".join(value for value in [organization_name, facility_name] if value)

    st.markdown(
        f"""
        <section class="dl-role-home">
          <div class="dl-role-home__kicker">OPERATIONS HOME</div>
          <h1>Good to see you, {safe_name}.</h1>
          <p>Your {html.escape(role_label)} workspace is organized around the work that needs attention now.</p>
          <div class="dl-role-home__context">{html.escape(context or 'Choose an organization and facility for tenant-scoped workflows.')}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    status_rows = build_data_hub_status(st.session_state)
    ready_sources = sum(row["Status"] == "Ready" for row in status_rows)
    retail_ready = sum(
        row["Status"] == "Ready" and row["Operations"] == "Retail Ops"
        for row in status_rows
    )
    metrics = st.columns(4)
    metrics[0].metric("Data sources ready", f"{ready_sources}/{len(status_rows)}")
    metrics[1].metric("Retail sources", retail_ready)
    metrics[2].metric("Facility", facility_name or "Not selected")
    metrics[3].metric("Doobie AI", "Connected" if ai_connected else "Not connected")

    st.markdown("### Start a task")
    st.caption("Open the right workspace without searching through menus.")
    actions = actions_for_role(normalized_role)
    for row_start in range(0, len(actions), 3):
        row = actions[row_start : row_start + 3]
        columns = st.columns(3)
        for column, action in zip(columns, row):
            with column:
                with st.container(border=True):
                    st.markdown(f"#### {action.label}")
                    st.caption(action.description)
                    if st.button(
                        "Open workspace",
                        key=f"home_action_{row_start}_{action.workspace}_{action.section}",
                        width="stretch",
                    ):
                        activate_home_action(st.session_state, action)
                        st.rerun()

    st.markdown("### Readiness")
    readiness = st.columns(3)
    with readiness[0]:
        with st.container(border=True):
            st.markdown("#### Company context")
            if organization_name and facility_name:
                st.success("Organization and facility are selected.")
            else:
                st.warning("Select an organization and facility in the sidebar.")
    with readiness[1]:
        with st.container(border=True):
            st.markdown("#### Operational data")
            if ready_sources:
                st.success(f"{ready_sources} source(s) are ready for use.")
            else:
                st.info("Open Data Import Center to load your first source.")
    with readiness[2]:
        with st.container(border=True):
            st.markdown("#### Support")
            st.write("Use the in-app guide for workflow instructions and field definitions.")
