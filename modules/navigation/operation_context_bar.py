"""Persistent organization, facility, and operation context for the flat shell.

The legacy access-context selector remains the tenant authority. This module
mirrors the same durable organization/facility records in the main viewport so
users do not depend on the Streamlit sidebar, especially on mobile.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

import streamlit as st

from modules.authentication.access_context import set_active_facility, set_active_organization
from services import app_user_store as app_user_store_module
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    EXTRACTION_WORKSPACE,
    WHITE_LABEL_WORKSPACE,
)


RETAIL_OPERATION = "Retail Ops"
PRODUCTION_OPERATION = "Production Ops"


def available_operation_modes(
    groups: Mapping[str, Sequence[str]], state: MutableMapping[str, Any]
) -> list[str]:
    """Return operation modes the current role can actually open."""

    workspaces = {workspace for options in groups.values() for workspace in options}
    role = str(state.get("auth_user_role") or "trial").strip().casefold()
    modes: list[str] = []
    if BUYER_WORKSPACE in workspaces and role in {
        "dev",
        "admin",
        "buyer",
        "supervisor",
        "operator",
        "qa",
        "read_only",
    }:
        modes.append(RETAIL_OPERATION)
    if workspaces.intersection({COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE}) and role in {
        "dev",
        "admin",
        "planner",
        "supervisor",
        "operator",
        "qa",
    }:
        modes.append(PRODUCTION_OPERATION)
    if not modes:
        modes.append(RETAIL_OPERATION)
    return modes


def _context_css() -> None:
    st.markdown(
        """
        <style>
        /* The persistent header owns tenant switching in flat mode. Keep the
           old controls instantiated for compatibility, but remove duplication. */
        .st-key-dev_org_context,
        .st-key-facility_context,
        .st-key-mobile_access_context { display:none !important; }

        .st-key-workspace_context_bar {
          margin:.05rem 0 .7rem !important;
          padding:.45rem .55rem !important;
          border:1px solid rgba(255,255,255,.08) !important;
          border-radius:13px !important;
          background:linear-gradient(145deg,#111,#0c0c0c) !important;
          box-shadow:0 8px 28px rgba(0,0,0,.18) !important;
        }
        .st-key-workspace_context_bar [data-testid="stHorizontalBlock"] {
          align-items:end !important;
          gap:.48rem !important;
        }
        .st-key-workspace_context_bar [data-testid="stWidgetLabel"] p {
          color:#8e8882 !important;
          font-size:.62rem !important;
          font-weight:780 !important;
          letter-spacing:.08em !important;
          text-transform:uppercase !important;
        }
        .st-key-workspace_context_bar [data-baseweb="select"] > div {
          min-height:38px !important;
          background:#101010 !important;
          border:1px solid rgba(255,255,255,.11) !important;
          border-radius:9px !important;
        }
        .dl-context-status {
          display:flex;align-items:center;gap:.48rem;min-height:38px;
          padding:0 .65rem;border:1px solid rgba(255,255,255,.08);
          border-radius:9px;background:#0d0d0d;color:#aaa49e !important;
          font-size:.72rem;font-weight:700;white-space:nowrap;
        }
        .dl-context-status::before {
          content:"";width:7px;height:7px;border-radius:50%;background:#4cd388;
          box-shadow:0 0 0 4px rgba(76,211,136,.10);
        }
        @media (max-width:768px) {
          .st-key-workspace_context_bar {padding:.5rem !important;margin-bottom:.5rem !important;}
          .st-key-workspace_context_bar [data-testid="stHorizontalBlock"] {flex-wrap:wrap !important;}
          .st-key-workspace_context_bar [data-testid="column"] {min-width:min(100%,145px) !important;flex:1 1 145px !important;}
          .st-key-workspace_context_bar [data-testid="column"]:first-child {flex-basis:100% !important;}
          .dl-context-status {min-height:34px;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _fallback_bar(state: MutableMapping[str, Any], modes: Sequence[str]) -> str:
    current = str(state.get("active_operation_mode") or modes[0])
    if current not in modes:
        current = modes[0]
        state["active_operation_mode"] = current
    with st.container(key="workspace_context_bar"):
        cols = st.columns([1.2, 1.4, 1.4, 1.0])
        cols[0].markdown('<div class="dl-context-status">Context connected</div>', unsafe_allow_html=True)
        cols[1].text_input("Organization", value=str(state.get("active_organization_name") or "Not selected"), disabled=True)
        cols[2].text_input("Facility", value=str(state.get("active_facility_name") or "Not selected"), disabled=True)
        selected = cols[3].selectbox("Operation", list(modes), index=list(modes).index(current), key="header_operation_context_fallback")
    state["active_operation_mode"] = selected
    return selected


def render_operation_context_bar(
    groups: Mapping[str, Sequence[str]], state: MutableMapping[str, Any]
) -> str:
    """Render the persistent top-right tenant + operation switcher."""

    _context_css()
    modes = available_operation_modes(groups, state)
    current_mode = str(state.get("active_operation_mode") or "")
    if current_mode not in modes:
        current_mode = modes[0]
        state["active_operation_mode"] = current_mode

    try:
        user_store = app_user_store_module.AppUserStore()
        role = str(state.get("auth_user_role") or "trial").strip().casefold()
        user_id = state.get("auth_user_id")
        assigned_org_id = state.get("auth_organization_id")
        organizations = user_store.list_organizations(active_only=False)
        organizations_by_id = {str(item.id): item for item in organizations}

        if role == "dev":
            if not any(str(getattr(item, "slug", "")) == "dev-sandbox" for item in organizations):
                try:
                    user_store.ensure_dev_sandbox()
                    organizations = user_store.list_organizations(active_only=False)
                    organizations_by_id = {str(item.id): item for item in organizations}
                except Exception:
                    pass
            visible_orgs = [
                item
                for item in organizations
                if str(getattr(item, "slug", "")) != "doobielogic-demo-simulation"
            ]
        else:
            selected_assigned = organizations_by_id.get(str(assigned_org_id or ""))
            visible_orgs = [selected_assigned] if selected_assigned is not None else []

        if not visible_orgs:
            return _fallback_bar(state, modes)

        current_org_id = str(state.get("active_organization_id") or "")
        selected_org = next(
            (item for item in visible_orgs if str(item.id) == current_org_id),
            next((item for item in visible_orgs if str(getattr(item, "slug", "")) == "dev-sandbox"), visible_orgs[0]),
        )
        facilities = user_store.list_facilities(
            selected_org.id,
            user_id=user_id if role not in {"dev", "admin"} else None,
        )
        if not facilities:
            return _fallback_bar(state, modes)
        current_facility_id = str(state.get("active_facility_id") or "")
        selected_facility = next(
            (item for item in facilities if str(item.id) == current_facility_id),
            next((item for item in facilities if str(getattr(item, "code", "")).casefold() == "sandbox"), facilities[0]),
        )

        org_labels = {
            ("DEV Sandbox" if str(getattr(item, "slug", "")) == "dev-sandbox" else str(item.name)): item
            for item in visible_orgs
        }
        facility_labels = {str(item.name): item for item in facilities}
        active_org_label = next(label for label, item in org_labels.items() if str(item.id) == str(selected_org.id))
        active_facility_label = next(label for label, item in facility_labels.items() if str(item.id) == str(selected_facility.id))

        for key, value in (
            ("header_org_context", active_org_label),
            ("header_facility_context", active_facility_label),
            ("header_operation_context", current_mode),
        ):
            if state.get(key) != value:
                state[key] = value

        def sync_org() -> None:
            item = org_labels.get(str(state.get("header_org_context") or ""))
            if item is not None:
                set_active_organization(state, item)
                state.pop("_context_hydrated_scope", None)

        def sync_facility() -> None:
            item = facility_labels.get(str(state.get("header_facility_context") or ""))
            if item is not None:
                set_active_facility(state, item)
                state.pop("_context_hydrated_scope", None)

        def sync_operation() -> None:
            selected = str(state.get("header_operation_context") or modes[0])
            if selected in modes:
                state["active_operation_mode"] = selected
                current_category = str(state.get("flat_navigation_section") or "")
                if selected == PRODUCTION_OPERATION and current_category in {"Purchasing"}:
                    state["flat_navigation_section"] = "Inventory"
                elif selected == RETAIL_OPERATION and current_category == "Production":
                    state["flat_navigation_section"] = "Inventory"

        is_sandbox = str(getattr(selected_org, "slug", "")) == "dev-sandbox"
        status_label = "Sandbox synced" if is_sandbox else "Facility synced"
        with st.container(key="workspace_context_bar"):
            cols = st.columns([1.2, 1.4, 1.4, 1.0])
            cols[0].markdown(f'<div class="dl-context-status">{status_label}</div>', unsafe_allow_html=True)
            if role == "dev":
                cols[1].selectbox("Organization", list(org_labels), key="header_org_context", on_change=sync_org)
            else:
                cols[1].text_input("Organization", value=active_org_label, disabled=True, key="header_org_context_readonly")
            cols[2].selectbox("Facility", list(facility_labels), key="header_facility_context", on_change=sync_facility)
            cols[3].selectbox("Operation", list(modes), key="header_operation_context", on_change=sync_operation)
        return str(state.get("active_operation_mode") or current_mode)
    except Exception:
        return _fallback_bar(state, modes)
