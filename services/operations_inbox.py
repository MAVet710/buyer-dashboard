"""Deterministic cross-workspace Operations Inbox for Buyer Dashboard.

The inbox ranks operational exceptions from the same tenant-scoped session data
that drives the existing workspaces. AI may explain these items later, but it is
never the source of truth for priority or operational state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import re
from typing import Any, Mapping, Sequence

import pandas as pd

from services.workspace_navigation import (
    BUYER_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    INVENTORY_COUNTS_SECTION,
    METRC_INTEGRATIONS_SECTION,
    RETAIL_OPS,
)


PRODUCT_ALIASES = (
    "product",
    "product name",
    "product_name",
    "item name",
    "item_name",
    "name",
    "sku name",
)
DOH_ALIASES = (
    "doh",
    "daysonhand",
    "days on hand",
    "days_of_cover",
    "days of cover",
)
VELOCITY_ALIASES = (
    "avgunitsperday",
    "avg units per day",
    "daily velocity",
    "units per day",
)
AVAILABLE_ALIASES = (
    "available",
    "on hand",
    "onhand",
    "on hand units",
    "quantity",
    "qty",
)
COST_ALIASES = ("unit cost", "unit_cost", "cost", "cogs", "wholesale")
ATTENTION_ALIASES = ("attention", "risk", "inventory risk", "alert")
EXPIRY_DAYS_ALIASES = ("days to expiry", "days_to_expiry", "days until expiration")
EXPIRY_DATE_ALIASES = (
    "expiration date",
    "expiration",
    "expires",
    "expiry date",
    "expiry",
)
ORDER_TYPE_ALIASES = ("order type", "order_type", "type")
ORDER_STATUS_ALIASES = ("status", "order status", "order_status")
ORDER_VALUE_ALIASES = ("order value", "order_value", "total", "total value", "amount")
ORDER_DUE_ALIASES = ("due date", "due_at", "due", "expected date", "expected_at")
ORDER_NUMBER_ALIASES = ("order number", "order_number", "po number", "po_number")
PARTNER_ALIASES = ("vendor", "vendor name", "partner", "partner name", "supplier")


SEVERITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}


@dataclass(frozen=True)
class InboxItem:
    """One deterministic operational exception with a route back to source."""

    key: str
    area: str
    title: str
    detail: str
    severity: str
    score: float
    financial_impact: float = 0.0
    route_group: str = ""
    route_workspace: str = ""
    route_section: str = ""
    action_label: str = "Review"
    product_name: str = ""
    evidence: tuple[str, ...] = ()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def _column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    if frame is None or frame.empty:
        return None
    lookup = {_norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        found = lookup.get(_norm(alias))
        if found:
            return found
    return None


def _first_frame(state: Mapping[str, Any], *keys: str) -> pd.DataFrame:
    for key in keys:
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy()
    return pd.DataFrame()


def _number(series: pd.Series | Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series(dtype=float)
    clean = (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    return pd.to_numeric(clean, errors="coerce")


def _row_number(row: pd.Series, column: str | None, default: float = 0.0) -> float:
    if not column:
        return float(default)
    value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
    return float(default if pd.isna(value) else value)


def _product_label(row: pd.Series, product_col: str | None, fallback: str) -> str:
    value = str(row.get(product_col) or "").strip() if product_col else ""
    return value or fallback


def _inventory_items(state: Mapping[str, Any], today: date) -> list[InboxItem]:
    frame = _first_frame(
        state,
        "detail_product_cached_df",
        "active_inventory_df",
        "inv_raw_df",
        "demo_inventory_df",
    )
    if frame.empty:
        return []

    product_col = _column(frame, PRODUCT_ALIASES)
    doh_col = _column(frame, DOH_ALIASES)
    velocity_col = _column(frame, VELOCITY_ALIASES)
    available_col = _column(frame, AVAILABLE_ALIASES)
    cost_col = _column(frame, COST_ALIASES)
    attention_col = _column(frame, ATTENTION_ALIASES)
    expiry_days_col = _column(frame, EXPIRY_DAYS_ALIASES)
    expiry_date_col = _column(frame, EXPIRY_DATE_ALIASES)

    work = frame.copy()
    if doh_col:
        work["__doh"] = _number(work[doh_col])
    else:
        work["__doh"] = math.nan
    if velocity_col:
        work["__velocity"] = _number(work[velocity_col]).fillna(0.0)
    else:
        work["__velocity"] = 0.0
    if available_col:
        work["__available"] = _number(work[available_col]).fillna(0.0)
    else:
        work["__available"] = 0.0
    if cost_col:
        work["__cost"] = _number(work[cost_col]).fillna(0.0)
    else:
        work["__cost"] = 0.0

    if expiry_days_col:
        work["__expiry_days"] = _number(work[expiry_days_col])
    elif expiry_date_col:
        expiry_dates = pd.to_datetime(work[expiry_date_col], errors="coerce").dt.date
        work["__expiry_days"] = expiry_dates.map(
            lambda value: (value - today).days if pd.notna(value) else math.nan
        )
    else:
        work["__expiry_days"] = math.nan

    items: list[InboxItem] = []
    for index, row in work.iterrows():
        product = _product_label(row, product_col, f"Inventory row {index + 1}")
        doh = _row_number(row, "__doh", math.nan)
        velocity = _row_number(row, "__velocity", 0.0)
        available = _row_number(row, "__available", 0.0)
        unit_cost = max(0.0, _row_number(row, "__cost", 0.0))
        inventory_value = max(0.0, available) * unit_cost
        attention = str(row.get(attention_col) or "").strip() if attention_col else ""
        expiry_days = _row_number(row, "__expiry_days", math.nan)

        if available <= 0 and velocity > 0:
            items.append(
                InboxItem(
                    key=f"stockout:{_norm(product)}",
                    area="Inventory",
                    title=f"{product} is out of stock",
                    detail="Recent sales velocity is present but no available inventory remains.",
                    severity="critical",
                    score=100.0 + min(20.0, velocity * 2.0),
                    financial_impact=inventory_value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="📊 Inventory Dashboard",
                    action_label="Open Inventory",
                    product_name=product,
                    evidence=(f"Available {available:g}", f"Daily velocity {velocity:.2f}"),
                )
            )
            continue

        if math.isfinite(doh) and velocity > 0 and doh <= 7:
            severity = "critical" if doh <= 3 else "high"
            urgency = max(0.0, 7.0 - doh)
            items.append(
                InboxItem(
                    key=f"low-cover:{_norm(product)}",
                    area="Inventory",
                    title=f"{product} has {doh:.1f} days of cover",
                    detail="Projected coverage is below the 7-day critical inventory threshold.",
                    severity=severity,
                    score=92.0 + urgency,
                    financial_impact=inventory_value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="📊 Inventory Dashboard",
                    action_label="Review Reorder",
                    product_name=product,
                    evidence=(f"DOH {doh:.1f}", f"Available {available:g}", f"Velocity {velocity:.2f}/day"),
                )
            )

        if math.isfinite(expiry_days) and 0 <= expiry_days <= 30 and available > 0:
            severity = "high" if expiry_days <= 14 else "medium"
            items.append(
                InboxItem(
                    key=f"expiry:{_norm(product)}",
                    area="Inventory",
                    title=f"{product} expires in {int(expiry_days)} days",
                    detail="Inventory is inside the 30-day expiration action window.",
                    severity=severity,
                    score=80.0 + max(0.0, 30.0 - expiry_days) / 3.0,
                    financial_impact=inventory_value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="📊 Inventory Dashboard",
                    action_label="Review Inventory",
                    product_name=product,
                    evidence=(f"Days to expiry {int(expiry_days)}", f"Inventory value ${inventory_value:,.2f}"),
                )
            )

        attention_norm = _norm(attention)
        if attention_norm in {"hold", "quarantine", "failed"}:
            items.append(
                InboxItem(
                    key=f"hold:{_norm(product)}",
                    area="Compliance",
                    title=f"{product} is on {attention or 'hold'}",
                    detail="A restricted inventory state needs review before the product can move or sell.",
                    severity="critical",
                    score=108.0,
                    financial_impact=inventory_value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="📊 Inventory Dashboard",
                    action_label="Investigate",
                    product_name=product,
                    evidence=(f"Attention {attention or 'Hold'}", f"Available {available:g}"),
                )
            )
        elif attention_norm in {"aging", "slow mover", "slow movers", "overstock"}:
            items.append(
                InboxItem(
                    key=f"aging:{_norm(product)}",
                    area="Inventory",
                    title=f"{product} needs sell-through attention",
                    detail=f"Inventory is flagged as {attention or 'aging / slow moving'}.",
                    severity="medium",
                    score=58.0 + min(15.0, inventory_value / 500.0),
                    financial_impact=inventory_value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="🐢 Slow Movers",
                    action_label="Review Slow Movers",
                    product_name=product,
                    evidence=(f"Inventory value ${inventory_value:,.2f}",),
                )
            )

    return items


def _commercial_items(state: Mapping[str, Any], today: date) -> list[InboxItem]:
    frame = _first_frame(
        state,
        "demo_commercial_orders_df",
        "commercial_orders_df",
        "active_commercial_orders_df",
    )
    if frame.empty:
        return []

    type_col = _column(frame, ORDER_TYPE_ALIASES)
    status_col = _column(frame, ORDER_STATUS_ALIASES)
    value_col = _column(frame, ORDER_VALUE_ALIASES)
    due_col = _column(frame, ORDER_DUE_ALIASES)
    number_col = _column(frame, ORDER_NUMBER_ALIASES)
    partner_col = _column(frame, PARTNER_ALIASES)

    items: list[InboxItem] = []
    for index, row in frame.iterrows():
        order_type = str(row.get(type_col) or "").strip().casefold() if type_col else ""
        if order_type and order_type != "purchase":
            continue
        status = str(row.get(status_col) or "").strip().casefold() if status_col else ""
        if status in {"fulfilled", "closed", "cancelled", "canceled", "received"}:
            continue
        value = max(0.0, _row_number(row, value_col, 0.0))
        order_number = str(row.get(number_col) or "").strip() if number_col else ""
        partner = str(row.get(partner_col) or "").strip() if partner_col else ""
        label = order_number or f"Purchase order {index + 1}"
        if partner:
            label = f"{label} · {partner}"

        due_days: int | None = None
        if due_col:
            due = pd.to_datetime(pd.Series([row.get(due_col)]), errors="coerce").iloc[0]
            if not pd.isna(due):
                due_days = (due.date() - today).days

        if due_days is not None and due_days < 0:
            items.append(
                InboxItem(
                    key=f"late-po:{_norm(order_number or str(index))}",
                    area="Purchasing",
                    title=f"{label} is {abs(due_days)} day(s) late",
                    detail="An inbound purchase order is past its expected due date and may affect stock coverage.",
                    severity="high",
                    score=86.0 + min(12.0, abs(due_days)),
                    financial_impact=value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="🚚 Delivery Impact",
                    action_label="Review Delivery",
                    evidence=(f"PO value ${value:,.2f}", f"Days late {abs(due_days)}"),
                )
            )
        elif due_days is not None and due_days <= 2:
            items.append(
                InboxItem(
                    key=f"due-po:{_norm(order_number or str(index))}",
                    area="Purchasing",
                    title=f"{label} is due soon",
                    detail="An open purchase order is due within two days.",
                    severity="medium",
                    score=66.0 + max(0, 2 - due_days),
                    financial_impact=value,
                    route_group=RETAIL_OPS,
                    route_workspace=BUYER_WORKSPACE,
                    route_section="🚚 Delivery Impact",
                    action_label="Review Delivery",
                    evidence=(f"PO value ${value:,.2f}", f"Due in {due_days} day(s)"),
                )
            )

    return items


def _data_items(status_rows: Sequence[Mapping[str, Any]]) -> list[InboxItem]:
    missing = [row for row in status_rows if str(row.get("Status") or "") != "Ready"]
    if not missing:
        return []
    labels = [
        str(row.get("Source") or row.get("Dataset") or row.get("Label") or "source")
        for row in missing[:4]
    ]
    return [
        InboxItem(
            key="data-readiness",
            area="Data",
            title=f"{len(missing)} operational source(s) need attention",
            detail=", ".join(labels),
            severity="high" if len(missing) >= 3 else "medium",
            score=72.0 + min(12.0, len(missing) * 2.0),
            route_group=DATA_OPERATIONS,
            route_workspace=DATA_HUB_WORKSPACE,
            action_label="Open Data Hub",
            evidence=tuple(labels),
        )
    ]


def _workflow_items(state: Mapping[str, Any]) -> list[InboxItem]:
    items: list[InboxItem] = []
    audit = state.get("inventory_audit_active") or state.get("active_inventory_audit")
    if audit:
        items.append(
            InboxItem(
                key="audit-in-progress",
                area="Audit",
                title="Inventory audit is still in progress",
                detail="Resume the existing count instead of starting another full recount.",
                severity="medium",
                score=68.0,
                route_group=RETAIL_OPS,
                route_workspace=BUYER_WORKSPACE,
                route_section=INVENTORY_COUNTS_SECTION,
                action_label="Resume Audit",
            )
        )

    sync_failures = state.get("metrc_sync_failures")
    if isinstance(sync_failures, pd.DataFrame):
        failure_count = len(sync_failures)
    elif isinstance(sync_failures, (list, tuple, set)):
        failure_count = len(sync_failures)
    elif isinstance(sync_failures, int):
        failure_count = max(0, sync_failures)
    else:
        failure_count = 0
    if failure_count:
        items.append(
            InboxItem(
                key="metrc-sync-failures",
                area="Compliance",
                title=f"{failure_count} Metrc sync action(s) failed",
                detail="External traceability state may differ from Buyer Dash and needs reconciliation.",
                severity="critical",
                score=115.0 + min(15.0, failure_count),
                route_group=RETAIL_OPS,
                route_workspace=BUYER_WORKSPACE,
                route_section=METRC_INTEGRATIONS_SECTION,
                action_label="Reconcile Metrc",
                evidence=(f"Failed actions {failure_count}",),
            )
        )
    return items


def build_operations_inbox(
    state: Mapping[str, Any],
    *,
    status_rows: Sequence[Mapping[str, Any]] = (),
    today: date | None = None,
    limit: int = 12,
) -> list[InboxItem]:
    """Build a ranked, deduplicated list of operational exceptions."""

    target_date = today or date.today()
    items = [
        *_workflow_items(state),
        *_inventory_items(state, target_date),
        *_commercial_items(state, target_date),
        *_data_items(status_rows),
    ]

    deduped: dict[str, InboxItem] = {}
    for item in items:
        existing = deduped.get(item.key)
        if existing is None or (
            SEVERITY_WEIGHT.get(item.severity, 0),
            item.score,
            item.financial_impact,
        ) > (
            SEVERITY_WEIGHT.get(existing.severity, 0),
            existing.score,
            existing.financial_impact,
        ):
            deduped[item.key] = item

    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            -SEVERITY_WEIGHT.get(item.severity, 0),
            -item.score,
            -item.financial_impact,
            item.area,
            item.title,
        ),
    )
    return ranked[: max(1, int(limit))]
