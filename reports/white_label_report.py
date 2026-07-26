from __future__ import annotations

import pandas as pd

from reports.executive_system import (
    ExecutiveReportSpec,
    RETAIL_PALETTE,
    ReportMetric,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import display_frame, frame


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        return pd.Series([0.0] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(0)


def _build_white_label_repack_report_pdf(payload: dict) -> bytes:
    payload = payload or {}
    summary = payload.get("summary") or {}
    raw_output = frame(payload.get("package_output_summary"))
    output = display_frame(
        raw_output,
        [
            ("Package Size", ["package size", "package_size_g", "package_size"]),
            ("Allocation %", ["allocation %", "allocation_pct"]),
            ("Grams Allocated", ["grams allocated", "grams_allocated"]),
            ("Units Produced", ["units", "units produced", "units_produced"]),
            ("Retail Price / Unit", ["retail price", "target retail price per unit", "target_retail_price_per_unit"]),
            ("Revenue", ["revenue"]),
            ("Packaging Cost", ["total packaging cost", "total_packaging_cost"]),
            ("Gross Profit", ["gross profit", "gross_profit"]),
            ("Gross Margin %", ["gross margin %", "gross_margin_pct"]),
            ("Status", ["status"]),
        ],
    )
    costs = frame(payload.get("cost_breakdown"))
    compliance = frame(payload.get("compliance_checklist"))
    readiness = payload.get("margin_readiness") or {}
    bulk = payload.get("bulk_lot_details") or {}

    revenue = float(summary.get("total_revenue_usd") or (_numeric(output, "Revenue").sum() if not output.empty else 0))
    landed_cost = float(summary.get("landed_cost_usd") or 0)
    gross_profit = float(summary.get("gross_profit_usd") or (_numeric(output, "Gross Profit").sum() if not output.empty else 0))
    gross_margin = float(summary.get("gross_margin_pct") or (gross_profit / revenue * 100 if revenue else 0))
    units = float(_numeric(output, "Units Produced").sum()) if not output.empty else 0
    packaging_cost = float(_numeric(output, "Packaging Cost").sum()) if "Packaging Cost" in output else 0
    usable_weight = float(
        bulk.get("wl_usable_weight_g")
        or (_numeric(output, "Grams Allocated").sum() if not output.empty else 0)
    )
    ready_count = int((compliance.get("Status", pd.Series(dtype=str)).astype(str).str.lower() == "ready").sum()) if not compliance.empty else 0
    review_count = int((compliance.get("Status", pd.Series(dtype=str)).astype(str).str.lower() != "ready").sum()) if not compliance.empty else 0

    findings = []
    if readiness.get("incomplete_rows", 0):
        findings.append(f"{int(readiness['incomplete_rows'])} package rows are missing required margin inputs.")
    if review_count:
        findings.append(f"{review_count} compliance checklist items still require attention.")
    if output.empty:
        findings.append("No package allocation output is available for this scenario.")
    if not findings:
        findings.append("Package economics and compliance inputs are complete for the current scenario.")

    recommendations = []
    if not output.empty and "Gross Profit" in output and "Package Size" in output:
        best = output.loc[_numeric(output, "Gross Profit").idxmax()]
        recommendations.append(f"Protect allocation to {best.get('Package Size')} where modeled gross profit is strongest.")
    if readiness.get("incomplete_rows", 0):
        recommendations.append("Complete missing retail-price and packaging-cost inputs before approving the package mix.")
    if review_count:
        recommendations.append("Resolve COA, source-lot, and label-review exceptions before launch.")
    if not recommendations:
        recommendations.append("Approve the modeled package mix and monitor actual yield against usable weight.")

    chart_items = []
    if not output.empty and "Package Size" in output and "Gross Profit" in output:
        profits = _numeric(output, "Gross Profit")
        chart_items = [
            (str(output.iloc[index]["Package Size"]), float(value), f"${value:,.0f} gross profit")
            for index, value in enumerate(profits.head(10))
        ]

    spec = ExecutiveReportSpec(
        title="White Label / Repack Executive Report",
        subtitle="Package allocation, margin performance, cost readiness, and launch compliance.",
        palette=RETAIL_PALETTE,
        organization=str(payload.get("organization") or bulk.get("wl_cultivator_name") or "Current retail operation"),
        facility=str(payload.get("facility") or "Retail repack"),
        reporting_period=str(payload.get("scenario_name") or "Current scenario"),
        metrics=[
            ReportMetric("Landed Cost", f"${landed_cost:,.0f}", "Bulk material cost"),
            ReportMetric("Modeled Revenue", f"${revenue:,.0f}", "Package-plan revenue"),
            ReportMetric("Gross Profit", f"${gross_profit:,.0f}", "Contribution before overhead"),
            ReportMetric("Gross Margin", f"{gross_margin:,.1f}%", "Modeled blended margin"),
            ReportMetric("Finished Units", f"{units:,.0f}", "Across package sizes"),
            ReportMetric("Usable Weight", f"{usable_weight:,.0f} g", "After modeled loss"),
            ReportMetric("Packaging Cost", f"${packaging_cost:,.0f}", "Packaging and labels"),
            ReportMetric("Compliance Ready", f"{ready_count}/{ready_count + review_count}", f"{review_count} items need review"),
        ],
        executive_brief=(
            f"The current package plan converts {usable_weight:,.0f} g into {units:,.0f} units, "
            f"producing ${gross_profit:,.0f} in modeled gross profit at a {gross_margin:,.1f}% blended margin."
        ),
        findings=findings,
        recommendations=recommendations,
        chart_title="Gross Profit by Package Size",
        chart_items=chart_items,
        sections=[
            ReportSection("Package Size Performance", output, "Modeled unit output and economics by package size.", max_rows=50),
            ReportSection("Cost Breakdown", costs, "Bulk, packaging, label, and labor cost contribution.", max_rows=40),
            ReportSection("Compliance Readiness", compliance, "Pre-launch documentation and label-review gates.", max_rows=50),
        ],
    )
    return build_executive_pdf(spec)
