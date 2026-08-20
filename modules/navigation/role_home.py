"""Role-aware operating home for fast, guided task entry."""

from __future__ import annotations

from dataclasses import dataclass
import html
from typing import Any, MutableMapping

import pandas as pd
import streamlit as st

from modules.data_hub import build_data_hub_status
from services.operations_inbox import InboxItem, build_operations_inbox
from services.traceability_inbox import build_traceability_inbox
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    METRC_INTEGRATIONS_SECTION,
    PRODUCTION_OPS,
    RETAIL_OPS,
    queue_workspace_navigation,
)


@dataclass(frozen=True)
class HomeAction:
    label: str
    description: str
    group: str = ""
    workspace: str = ""
    section: str = ""
    roles: tuple[str, ...] = ()
    intent: str = ""


HOME_ACTIONS = (
    HomeAction("Review inventory", "Stock health, reorders, and aging risk.", RETAIL_OPS, BUYER_WORKSPACE, "📊 Inventory Dashboard", ("dev", "admin", "buyer", "read_only")),
    HomeAction("Start inventory audit", "Scan, pause, resume, and reconcile counts.", RETAIL_OPS, BUYER_WORKSPACE, "📋 Inventory Counts", ("dev", "admin", "buyer", "supervisor", "operator", "qa")),
    HomeAction(
        "Traceability queue",
        "Review pending, rejected, and reconciliation-required state-system actions.",
        roles=("dev", "admin", "buyer", "supervisor", "operator", "qa", "read_only"),
        intent="traceability_console",
    ),
    HomeAction(
        "Open Package Studio",
        "Break down, pack down, build, sample, correct, and trace packages.",
        roles=("dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"),
        intent="package_studio",
    ),
    HomeAction("Build purchasing decisions", "Recommendations, budget, deliveries, and POs.", RETAIL_OPS, BUYER_WORKSPACE, "🧾 PO Builder", ("dev", "admin", "buyer")),
    HomeAction("Plan Co-Man production", "Balance orders, machines, crews, and hand labor.", PRODUCTION_OPS, COMAN_WORKSPACE, roles=("dev", "admin", "planner", "supervisor", "operator", "qa")),
    HomeAction("Review extraction", "Inspect run performance, yields, QA, and production risks.", PRODUCTION_OPS, EXTRACTION_WORKSPACE, roles=("dev", "admin", "planner", "supervisor", "operator", "qa")),
    HomeAction("Manage orders", "Track customer orders and fulfillment readiness.", COMMERCIAL_OPS, COMMERCIAL_WORKSPACE, roles=("dev", "admin", "buyer", "planner", "supervisor")),
    HomeAction("Import operational data", "Load, map, review, and reuse operational sources.", DATA_OPERATIONS, DATA_HUB_WORKSPACE),
)


def actions_for_role(role: str) -> tuple[HomeAction, ...]:
    normalized = str(role or "trial").strip().lower()
    return tuple(action for action in HOME_ACTIONS if not action.roles or normalized in action.roles)


def activate_home_action(state: MutableMapping[str, Any], action: HomeAction) -> None:
    if action.intent == "package_studio":
        state["package_studio_open"] = True
        return
    if action.intent == "traceability_console":
        state["traceability_console_open"] = True
        return
    queue_workspace_navigation(
        state,
        group=action.group,
        workspace=action.workspace,
        buyer_section=action.section,
    )


def activate_inbox_item(state: MutableMapping[str, Any], item: InboxItem) -> None:
    """Open the closest authoritative workflow for one Operations Inbox item."""

    if item.product_name and item.area == "Inventory":
        state["product_360_selected_name"] = item.product_name
        state["product_360_open"] = True
        return
    if (
        item.route_section == METRC_INTEGRATIONS_SECTION
        or item.key.startswith("metrc-")
        or item.key.startswith("traceability:")
    ):
        state["traceability_console_open"] = True
        return
    if item.route_group and item.route_workspace:
        queue_workspace_navigation(
            state,
            group=item.route_group,
            workspace=item.route_workspace,
            buyer_section=item.route_section,
        )


def _home_css() -> None:
    st.markdown(
        """
        <style>
        .dl-role-home {
            margin:.2rem 0 1rem;
            padding:.25rem .1rem .4rem;
        }
        .dl-role-home__kicker,
        .dl-home-section-label {
            color:#E7984E !important;
            font-size:.66rem;
            font-weight:820;
            letter-spacing:.14em;
            text-transform:uppercase;
        }
        .dl-role-home h1 {
            margin:.3rem 0 .35rem !important;
            font-size:clamp(2rem,4vw,3rem) !important;
        }
        .dl-role-home p {
            max-width:760px;
            margin:0 !important;
            color:#AAB4AC !important;
            font-size:.95rem;
        }
        .dl-role-home__context {
            display:inline-flex;
            margin-top:.7rem;
            padding:.28rem .6rem;
            color:#F4B36F !important;
            background:rgba(231,152,78,.08);
            border:1px solid rgba(231,152,78,.18);
            border-radius:999px;
            font-size:.7rem;
            font-weight:720;
        }
        [class*="st-key-home_metric_"] {
            padding:.7rem .78rem .62rem !important;
            border:1px solid rgba(255,255,255,.08) !important;
            border-radius:14px !important;
            background:linear-gradient(145deg,rgba(24,28,25,.96),rgba(17,20,18,.90)) !important;
            box-shadow:0 12px 30px rgba(0,0,0,.15) !important;
        }
        [class*="st-key-home_metric_"] [data-testid="stMetricValue"] {
            font-size:1.62rem !important;
            font-weight:800 !important;
        }
        [class*="st-key-home_task_card_"] {
            min-height:148px;
            padding:.78rem !important;
            border:1px solid rgba(255,255,255,.08) !important;
            border-radius:15px !important;
            background:linear-gradient(145deg,rgba(24,28,25,.94),rgba(17,20,18,.86)) !important;
        }
        [class*="st-key-home_task_card_"]:hover {
            border-color:rgba(231,152,78,.26) !important;
        }
        [class*="st-key-home_alert_"] {
            padding:.65rem .72rem !important;
            border:1px solid rgba(255,255,255,.075) !important;
            border-radius:12px !important;
            background:rgba(255,255,255,.025) !important;
        }
        .dl-home-alert-title {
            color:#F5F7F4 !important;
            font-size:.84rem;
            font-weight:760;
        }
        .dl-home-alert-detail {
            margin-top:.12rem;
            color:#AAB4AC !important;
            font-size:.75rem;
        }
        .dl-home-severity {
            display:inline-flex;
            margin-top:.15rem;
            padding:.12rem .36rem;
            border-radius:999px;
            border:1px solid rgba(255,255,255,.09);
            color:#B8C0BA !important;
            background:rgba(255,255,255,.03);
            font-size:.58rem;
            font-weight:820;
            letter-spacing:.08em;
            text-transform:uppercase;
        }
        .dl-home-evidence {
            margin-top:.16rem;
            color:#7F8982 !important;
            font-size:.65rem;
        }
        @media (max-width:768px) {
            .dl-role-home { margin-top:.05rem; }
            .dl-role-home h1 { font-size:2rem !important; }
            [class*="st-key-home_task_card_"] { min-height:auto; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame is None or frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _inventory_risk_count() -> int:
    frame = st.session_state.get("detail_product_cached_df")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return 0
    if "daysonhand" in frame.columns:
        doh = _numeric(frame, "daysonhand")
        velocity = _numeric(frame, "avgunitsperday") if "avgunitsperday" in frame.columns else pd.Series(1.0, index=frame.index)
        return int(((doh <= 7) & (velocity > 0)).sum())
    if "days_of_cover" in frame.columns:
        cover = _numeric(frame, "days_of_cover")
        return int((cover <= 7).sum())
    return 0


def _open_purchase_orders() -> tuple[int, float]:
    frame = st.session_state.get("demo_commercial_orders_df")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return 0, 0.0
    local = frame.copy()
    type_col = next((c for c in ("Order Type", "order_type") if c in local.columns), "")
    status_col = next((c for c in ("Status", "status") if c in local.columns), "")
    value_col = next((c for c in ("Order Value", "order_value", "Total", "total") if c in local.columns), "")
    if type_col:
        local = local[local[type_col].astype(str).str.casefold().eq("purchase")]
    if status_col:
        local = local[~local[status_col].astype(str).str.casefold().isin({"fulfilled", "closed", "cancelled", "canceled"})]
    total = float(pd.to_numeric(local[value_col], errors="coerce").fillna(0).sum()) if value_col else 0.0
    return int(len(local)), total


def _render_operations_inbox(items: list[InboxItem]) -> None:
    st.markdown('<div class="dl-home-section-label">NEEDS ATTENTION · OPERATIONS INBOX</div>', unsafe_allow_html=True)
    if not items:
        st.success("No high-priority operational exceptions are visible from the loaded facility data.")
        st.caption("Start from a task below or use global search.")
        return

    for idx, item in enumerate(items):
        with st.container(key=f"home_alert_{idx}"):
            area_col, body_col, action_col = st.columns([1.1, 5.2, 1.45])
            with area_col:
                st.caption(item.area.upper())
                st.markdown(
                    f'<span class="dl-home-severity">{html.escape(item.severity)}</span>',
                    unsafe_allow_html=True,
                )
            with body_col:
                st.markdown(
                    f'<div class="dl-home-alert-title">{html.escape(item.title)}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="dl-home-alert-detail">{html.escape(item.detail)}</div>',
                    unsafe_allow_html=True,
                )
                evidence = " · ".join(item.evidence)
                if evidence:
                    st.markdown(
                        f'<div class="dl-home-evidence">{html.escape(evidence)}</div>',
                        unsafe_allow_html=True,
                    )
            with action_col:
                if item.route_workspace or item.product_name:
                    if st.button(
                        item.action_label,
                        key=f"home_inbox_action_{idx}_{item.key}",
                        width="stretch",
                        type="primary" if item.severity == "critical" else "secondary",
                    ):
                        activate_inbox_item(st.session_state, item)
                        st.rerun()


def render_role_home(
    *,
    user_name: str,
    role: str,
    organization_name: str = "",
    facility_name: str = "",
    ai_connected: bool = False,
    ai_status: str = "not_connected",
) -> None:
    """Render the Option-B-style role home and task launcher."""

    _home_css()
    normalized_role = str(role or "trial").strip().lower()
    safe_name = html.escape(str(user_name or "Operator"))
    role_label = normalized_role.replace("_", " ").title()
    context = " · ".join(value for value in [organization_name, facility_name] if value)

    st.markdown(
        f"""
        <section class="dl-role-home">
          <div class="dl-role-home__kicker">OPERATIONS HOME</div>
          <h1>Good to see you, {safe_name}.</h1>
          <p>Your {html.escape(role_label)} workspace is organized around what needs attention now.</p>
          <div class="dl-role-home__context">{html.escape(context or 'Choose an organization and facility')}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    status_rows = build_data_hub_status(st.session_state)
    ready_sources = sum(row.get("Status") == "Ready" for row in status_rows)
    low_stock = _inventory_risk_count()
    open_po_count, open_po_total = _open_purchase_orders()
    base_inbox_items = build_operations_inbox(
        st.session_state,
        status_rows=status_rows,
        limit=12,
    )
    traceability_items = build_traceability_inbox(st.session_state, limit=6)
    if traceability_items:
        base_inbox_items = [item for item in base_inbox_items if item.key != "metrc-sync-failures"]
    inbox_items = sorted(
        [*traceability_items, *base_inbox_items],
        key=lambda item: item.score,
        reverse=True,
    )[:8]
    high_priority = sum(item.severity in {"critical", "high"} for item in inbox_items)

    metric_columns = st.columns(4)
    metric_values = (
        ("Needs attention", str(len(inbox_items)), f"{high_priority} high-priority item(s)"),
        ("Low stock", str(low_stock), "Critical cover signal"),
        ("Open POs", str(open_po_count), f"${open_po_total:,.0f} represented"),
        ("Data sources ready", f"{ready_sources}/{len(status_rows)}", "Sources available to workspaces"),
    )
    for idx, (column, metric) in enumerate(zip(metric_columns, metric_values)):
        label, value, caption = metric
        with column:
            with st.container(key=f"home_metric_{idx}"):
                st.metric(label, value)
                st.caption(caption)

    _render_operations_inbox(inbox_items)

    st.markdown('<div class="dl-home-section-label" style="margin-top:1rem">START A TASK</div>', unsafe_allow_html=True)
    actions = actions_for_role(normalized_role)
    for row_start in range(0, len(actions), 3):
        row = actions[row_start : row_start + 3]
        columns = st.columns(3)
        for offset, (column, action) in enumerate(zip(columns, row)):
            card_index = row_start + offset
            with column:
                with st.container(key=f"home_task_card_{card_index}"):
                    st.markdown(f"#### {action.label}")
                    st.caption(action.description)
                    if st.button(
                        "Open",
                        key=f"home_action_{card_index}_{action.intent or action.workspace}_{action.section}",
                        width="stretch",
                        type="primary" if card_index == 0 else "secondary",
                    ):
                        activate_home_action(st.session_state, action)
                        st.rerun()

    if bool(st.session_state.get("package_studio_open", False)):
        from modules.package_studio.ui import render_package_studio_dialog

        render_package_studio_dialog(st.session_state)

    if bool(st.session_state.get("traceability_console_open", False)):
        from modules.traceability.ui import render_traceability_console_dialog

        render_traceability_console_dialog(st.session_state)

    normalized_ai_status = str(ai_status or "not_connected").strip().lower()
    ai_label = "Connected" if ai_connected else ("Waking up" if normalized_ai_status == "waking_up" else "Not connected")
    st.caption(f"Doobie AI: {ai_label} · Operations Inbox and all task routes remain usable without AI.")
