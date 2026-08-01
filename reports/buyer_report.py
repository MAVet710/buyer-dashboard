from __future__ import annotations

import pandas as pd

from reports.executive_system import (
    ExecutiveReportSpec,
    RETAIL_PALETTE,
    ReportMetric,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import (
    display_frame,
    first_present,
    frame,
    numeric_mean,
    numeric_series,
    numeric_sum,
)


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _build_buyer_executive_report_pdf(payload: dict) -> bytes:
    payload = payload or {}
    detail = frame(payload.get("detail_view"))
    if detail.empty:
        detail = frame(payload.get("product_detail"))
    inventory = frame(payload.get("inv_df"))
    if inventory.empty:
        inventory = frame(payload.get("inventory_health"))
    if inventory.empty:
        inventory = frame(payload.get("inv_summary"))
    sales = frame(payload.get("sales_df"))
    if sales.empty:
        sales = frame(payload.get("sales_summary"))
    kpis = payload.get("kpis") or payload.get("buyer_kpis") or {}

    units_sold = float(first_present(kpis, ["total_units_sold"], numeric_sum(sales, "units sold", "unitssold")))
    units_on_hand = float(
        first_present(kpis, ["total_units_on_hand", "total_on_hand_units"], numeric_sum(inventory, "on hand units", "onhandunits", "on hand"))
    )
    inventory_value = float(
        first_present(kpis, ["total_inventory_value"], numeric_sum(inventory, "inventory value", "inventoryvalue"))
    )
    avg_doh = float(first_present(kpis, ["avg_days_on_hand", "avg_dos"], numeric_mean(detail, "days on hand", "daysonhand")))
    reorder_qty = float(
        first_present(kpis, ["total_reorder_qty", "total_reorder_need"], numeric_sum(detail, "reorder qty", "reorderqty"))
    )
    reorder_series = numeric_series(detail, "reorder qty", "reorderqty")
    doh_series = numeric_series(detail, "days on hand", "daysonhand")
    velocity_series = numeric_series(detail, "avg units per day", "avgunitsperday")
    reorder_skus = int((reorder_series > 0).sum())
    at_risk = int(((doh_series > 0) & (doh_series <= 7)).sum())
    overstock = int((doh_series >= 60).sum())
    slow_movers = int((velocity_series <= 0).sum()) if not detail.empty else 0
    health_score = max(0, min(100, int(100 - reorder_skus * 2 - at_risk * 3 - slow_movers)))

    has_data = not detail.empty or not inventory.empty or not sales.empty
    findings = []
    if not has_data:
        findings.append("No inventory or sales dataset is available for this report.")
    if reorder_skus:
        findings.append(f"{reorder_skus} SKUs require replenishment decisions.")
    if at_risk:
        findings.append(f"{at_risk} SKUs have seven days of supply or less.")
    if overstock:
        findings.append(f"{overstock} SKUs are holding at least 60 days of inventory.")
    if slow_movers:
        findings.append(f"{slow_movers} SKUs show no current sales velocity.")
    if not findings:
        findings.append("No material inventory exceptions were detected in the current dataset.")

    recommendations = []
    if not has_data:
        recommendations.append("Upload current inventory and sales data before making a purchasing decision.")
    if at_risk:
        recommendations.append("Prioritize low-cover items before the next purchase cycle closes.")
    if reorder_skus:
        recommendations.append("Validate reorder quantities against inbound POs and vendor lead times.")
    if overstock or slow_movers:
        recommendations.append("Pause buying on excess inventory and build a markdown or transfer plan.")
    if not recommendations:
        recommendations.append("Maintain the current buying cadence and review exceptions weekly.")

    detail_display = display_frame(
        detail,
        [
            ("Product Name", ["product name", "product_name", "product", "item name", "item"]),
            ("Category", ["category"]),
            ("On Hand", ["on hand", "onhand", "on hand units"]),
            ("Units Sold", ["units sold", "unitssold"]),
            ("Avg Units/Day", ["avg units per day", "avgunitsperday"]),
            ("Days on Hand", ["days on hand", "daysonhand"]),
            ("Reorder Qty", ["reorder qty", "reorderqty"]),
        ],
    )
    if not detail_display.empty:
        doh = pd.to_numeric(detail_display.get("Days on Hand"), errors="coerce").fillna(0)
        sold = pd.to_numeric(detail_display.get("Units Sold"), errors="coerce").fillna(0)
        on_hand = pd.to_numeric(detail_display.get("On Hand"), errors="coerce").fillna(0)
        detail_display["Inventory Status"] = "Healthy"
        detail_display.loc[(doh > 0) & (doh <= 7), "Inventory Status"] = "Critical"
        detail_display.loc[(doh > 7) & (doh <= 21), "Inventory Status"] = "Watch"
        detail_display.loc[doh >= 60, "Inventory Status"] = "Overstock"
        detail_display.loc[(sold <= 0) & (on_hand > 0), "Inventory Status"] = "No Movement"

    reorder_actions = (
        detail_display[pd.to_numeric(detail_display.get("Reorder Qty"), errors="coerce").fillna(0) > 0]
        .sort_values("Reorder Qty", ascending=False)
        if not detail_display.empty and "Reorder Qty" in detail_display
        else pd.DataFrame()
    )
    risk_rows = (
        detail_display[detail_display.get("Inventory Status", pd.Series(dtype=str)).isin(["Critical", "Overstock", "No Movement"])]
        if not detail_display.empty
        else pd.DataFrame()
    )

    category_chart: list[tuple[str, float, str]] = []
    if not detail_display.empty and "Category" in detail_display and "On Hand" in detail_display:
        grouped = (
            detail_display.assign(**{"On Hand": pd.to_numeric(detail_display["On Hand"], errors="coerce").fillna(0)})
            .groupby("Category", dropna=False)["On Hand"]
            .sum()
            .sort_values(ascending=False)
            .head(8)
        )
        category_chart = [(str(label), float(value), f"{value:,.0f} units") for label, value in grouped.items()]

    store_name = str(payload.get("store_name") or payload.get("organization") or "Current retail operation")
    reporting_period = str(payload.get("reporting_period") or "Current session")
    spec = ExecutiveReportSpec(
        title="Buyer Operations Executive Report",
        subtitle="Inventory health, purchasing pressure, and immediate buyer actions.",
        palette=RETAIL_PALETTE,
        organization=store_name,
        facility=str(payload.get("facility") or "Retail"),
        reporting_period=reporting_period,
        metrics=[
            ReportMetric("Inventory Value", _money(inventory_value), "Current on-hand valuation"),
            ReportMetric("Units Sold", f"{units_sold:,.0f}", "Reporting-period movement"),
            ReportMetric("Units On Hand", f"{units_on_hand:,.0f}", "Current inventory"),
            ReportMetric("Average Days On Hand", f"{avg_doh:,.1f}", "Across analyzed SKUs"),
            ReportMetric("Reorder Need", f"{reorder_qty:,.0f}", f"{reorder_skus} affected SKUs"),
            ReportMetric("Inventory Health", f"{health_score}/100", "Exception-weighted score"),
            ReportMetric("At-Risk SKUs", f"{at_risk}", "Seven days or less"),
            ReportMetric("Overstock SKUs", f"{overstock}", "Sixty days or more"),
        ],
        executive_brief=(
            (
                f"Inventory health is {health_score}/100. The immediate decision queue contains "
                f"{reorder_skus} replenishment candidates, {at_risk} critical-cover SKUs, and "
                f"{overstock} excess-inventory SKUs."
            )
            if has_data
            else "This report was generated without inventory or sales data; operating conclusions are not yet available."
        ),
        findings=findings,
        recommendations=recommendations,
        chart_title="On-Hand Inventory by Category",
        chart_items=category_chart,
        sections=[
            ReportSection(
                "Reorder Action List",
                reorder_actions,
                "Items with a calculated replenishment requirement, ranked by recommended quantity.",
                max_rows=50,
            ),
            ReportSection(
                "Inventory Exceptions",
                risk_rows,
                "Critical stock, overstock, and no-movement items requiring a buyer decision.",
                max_rows=50,
            ),
            ReportSection(
                "Product Performance Detail",
                detail_display,
                "Supporting inventory and velocity detail for the current analysis.",
                max_rows=80,
            ),
        ],
    )
    return build_executive_pdf(spec)


def _build_buyer_executive_report_bytes(payload: dict) -> bytes:
    return _build_buyer_executive_report_pdf(payload)
