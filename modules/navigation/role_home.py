"""Role-aware operating home for fast, guided task entry."""

from __future__ import annotations

from dataclasses import dataclass
import html
import math
from typing import Any, MutableMapping

import pandas as pd
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
    HomeAction("Review inventory", "Stock health, reorders, and aging risk.", RETAIL_OPS, BUYER_WORKSPACE, "📊 Inventory Dashboard", ("dev", "admin", "buyer", "read_only")),
    HomeAction("Start inventory audit", "Scan, pause, resume, and reconcile counts.", RETAIL_OPS, BUYER_WORKSPACE, "📋 Inventory Counts", ("dev", "admin", "buyer", "supervisor", "operator", "qa")),
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
    queue_workspace_navigation(
        state,
        group=action.group,
        workspace=action.workspace,
        buyer_section=action.section,
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


def _attention_rows(status_rows: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    low_stock = _inventory_risk_count()
    if low_stock:
        rows.append(("Inventory", f"{low_stock} critical low-cover SKU(s)", "Open Inventory to review replenishment risk."))

    open_po_count, open_po_total = _open_purchase_orders()
    if open_po_count:
        rows.append(("Purchasing", f"{open_po_count} open purchase order(s)", f"${open_po_total:,.0f} currently represented in the loaded order data."))

    missing = [row for row in status_rows if row.get("Status") != "Ready"]
    if missing:
        labels = ", ".join(str(row.get("Source") or row.get("Dataset") or "source") for row in missing[:3])
        rows.append(("Data", f"{len(missing)} source(s) need attention", labels))

    audit_state = st.session_state.get("inventory_audit_active") or st.session_state.get("active_inventory_audit")
    if audit_state:
        rows.append(("Audit", "Inventory audit in progress", "Resume the current count instead of starting over."))

    if not rows:
        rows.append(("Ready", "No high-priority operational exceptions detected", "Start from a task below or use global search."))
    return rows[:4]


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

    metric_columns = st.columns(4)
    metric_values = (
        ("Data sources ready", f"{ready_sources}/{len(status_rows)}", "Sources available to workspaces"),
        ("Low stock", str(low_stock), "Critical cover signal"),
        ("Open POs", str(open_po_count), f"${open_po_total:,.0f} represented"),
        ("Facility", facility_name or "Not selected", "Tenant-scoped workspace"),
    )
    for idx, (column, metric) in enumerate(zip(metric_columns, metric_values)):
        label, value, caption = metric
        with column:
            with st.container(key=f"home_metric_{idx}"):
                st.metric(label, value)
                st.caption(caption)

    st.markdown('<div class="dl-home-section-label">NEEDS ATTENTION</div>', unsafe_allow_html=True)
    for idx, (area, title, detail) in enumerate(_attention_rows(status_rows)):
        with st.container(key=f"home_alert_{idx}"):
            left, right = st.columns([1, 5])
            with left:
                st.caption(area.upper())
            with right:
                st.markdown(f'<div class="dl-home-alert-title">{html.escape(title)}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="dl-home-alert-detail">{html.escape(detail)}</div>', unsafe_allow_html=True)

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
                        key=f"home_action_{card_index}_{action.workspace}_{action.section}",
                        width="stretch",
                        type="primary" if card_index == 0 else "secondary",
                    ):
                        activate_home_action(st.session_state, action)
                        st.rerun()

    normalized_ai_status = str(ai_status or "not_connected").strip().lower()
    ai_label = "Connected" if ai_connected else ("Waking up" if normalized_ai_status == "waking_up" else "Not connected")
    st.caption(f"Doobie AI: {ai_label} · Global search and all task routes remain usable without AI.")
