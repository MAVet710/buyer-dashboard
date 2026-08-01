from __future__ import annotations

from reports.executive_system import (
    ExecutiveReportSpec,
    RETAIL_PALETTE,
    ReportMetric,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import first_present, frame, resolve_column


def _build_retail_ops_executive_report_pdf(payload: dict) -> bytes:
    payload = payload or {}
    metrics = payload.get("metrics") or {}
    analysis = frame(payload.get("analysis"))
    demand = frame(payload.get("demand"))
    staffing = frame(payload.get("staffing"))
    for product_frame in (analysis, demand):
        if "Product Name" not in product_frame.columns:
            product_column = resolve_column(
                product_frame,
                "product name",
                "product_name",
                "product",
                "item name",
            )
            if product_column is not None:
                product_frame.rename(columns={product_column: "Product Name"}, inplace=True)

    labor_cost = float(first_present(metrics, ["total_labor_cost"], 0))
    labor_hours = float(first_present(metrics, ["total_labor_hours"], 0))
    labor_pct = float(first_present(metrics, ["labor_pct_of_sales", "labor_pct"], 0))
    sales_per_hour = float(first_present(metrics, ["sales_per_labor_hour"], 0))
    tx_per_hour = float(first_present(metrics, ["transactions_per_labor_hour", "tx_per_labor_hour"], 0))
    total_sales = float(first_present(metrics, ["total_sales"], 0))
    status = str(first_present(metrics, ["labor_health_status", "status"], "Data Incomplete"))
    heavy_hours = int(first_present(metrics, ["heavy_hours"], 0))
    lean_hours = int(first_present(metrics, ["lean_hours"], 0))

    findings = list(payload.get("findings") or payload.get("summary_lines") or [])
    recommendations = list(payload.get("recommendations") or [])
    if not findings:
        findings = [f"Labor health is {status}; {heavy_hours} heavy and {lean_hours} lean operating windows were identified."]
    if not recommendations:
        recommendations = ["Upload current schedule and demand data to unlock staffing recommendations."]

    chart_items = []
    if not analysis.empty and "schedule_status" in analysis:
        counts = analysis["schedule_status"].astype(str).value_counts()
        chart_items = [(str(label), float(value), f"{int(value)} operating hours") for label, value in counts.items()]

    spec = ExecutiveReportSpec(
        title="Retail Labor Operations Executive Report",
        subtitle="Staffing efficiency, demand alignment, labor cost, and operating-window actions.",
        palette=RETAIL_PALETTE,
        organization=str(payload.get("organization") or "Current retail operation"),
        facility=str(payload.get("facility") or "Retail location"),
        reporting_period=str(payload.get("reporting_period") or "Current session"),
        metrics=[
            ReportMetric("Total Labor Cost", f"${labor_cost:,.0f}", "Scheduled labor"),
            ReportMetric("Labor Hours", f"{labor_hours:,.1f}", "Scheduled coverage"),
            ReportMetric("Labor % of Sales", f"{labor_pct:,.1f}%", "Current demand basis"),
            ReportMetric("Sales / Labor Hour", f"${sales_per_hour:,.0f}", "Productivity"),
            ReportMetric("Transactions / Labor Hour", f"{tx_per_hour:,.1f}", "Service workload"),
            ReportMetric("Demand Sales", f"${total_sales:,.0f}", "Analyzed demand"),
            ReportMetric("Heavy Windows", f"{heavy_hours}", "Potential overstaffing"),
            ReportMetric("Lean Windows", f"{lean_hours}", f"Status: {status}"),
        ],
        executive_brief=(
            f"Retail labor is currently classified as {status}. The analyzed schedule contains "
            f"{heavy_hours} heavy windows and {lean_hours} lean windows, producing "
            f"${sales_per_hour:,.0f} in demand sales per labor hour."
        ),
        findings=findings,
        recommendations=recommendations,
        chart_title="Labor Alignment by Operating Status",
        chart_items=chart_items,
        sections=[
            ReportSection("Lean vs. Heavy Analysis", analysis, "Hourly or daily labor alignment against sales demand.", max_rows=80),
            ReportSection("Demand Detail", demand, "Sales and transaction demand used in the staffing analysis.", max_rows=80),
            ReportSection("Staffing Detail", staffing, "Scheduled coverage and labor-cost inputs.", max_rows=80),
        ],
    )
    return build_executive_pdf(spec)
