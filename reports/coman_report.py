from __future__ import annotations

import pandas as pd

from reports.executive_system import (
    ExecutiveReportSpec,
    PRODUCTION_PALETTE,
    ReportMetric,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import frame


def _build_coman_executive_report_pdf(payload: dict) -> bytes:
    payload = payload or {}
    orders = frame(payload.get("orders"))
    actuals = frame(payload.get("actuals"))
    machines = frame(payload.get("machines"))
    crew = frame(payload.get("crew"))
    customers = frame(payload.get("customers"))

    status_series = orders.get("Status", pd.Series(dtype=str)).astype(str).str.lower()
    open_orders = int((~status_series.isin(["complete", "completed", "cancelled"])).sum()) if not orders.empty else 0
    planned_units = float(pd.to_numeric(orders.get("Units", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    external_jobs = int(orders.get("Type", pd.Series(dtype=str)).astype(str).str.lower().eq("external").sum()) if not orders.empty else 0
    late_jobs = 0
    if not orders.empty and "Due" in orders:
        due = pd.to_datetime(orders["Due"], errors="coerce")
        late_jobs = int(((due < pd.Timestamp.now().normalize()) & ~status_series.isin(["complete", "completed", "cancelled"])).sum())

    completed_jobs = len(actuals)
    actual_units = float(pd.to_numeric(actuals.get("Actual Units", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    scrap = float(pd.to_numeric(actuals.get("Scrap", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    labor_hours = float(pd.to_numeric(actuals.get("Labor Hours", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    attainment = float(pd.to_numeric(actuals.get("Attainment %", pd.Series(dtype=float)), errors="coerce").fillna(0).mean()) if not actuals.empty else 0

    has_data = not orders.empty or not actuals.empty or not machines.empty or not crew.empty
    findings = []
    if not has_data:
        findings.append("No Co-Man orders, actuals, machines, or crew capacity are available.")
    if late_jobs:
        findings.append(f"{late_jobs} open production jobs are past their due date.")
    if scrap:
        findings.append(f"{scrap:,.0f} units of scrap have been recorded across completed jobs.")
    if machines.empty:
        findings.append("No facility machines are available for capacity reporting.")
    if not findings:
        findings.append("No material schedule, scrap, or equipment exceptions were detected.")

    recommendations = []
    if not has_data:
        recommendations.append("Create the production queue and resource records before using this report for scheduling.")
    if late_jobs:
        recommendations.append("Re-sequence overdue work against crew and machine availability.")
    if scrap:
        recommendations.append("Review scrap drivers by product, machine, and shift before the next run.")
    if machines.empty:
        recommendations.append("Configure facility machines and observed rates to unlock capacity decisions.")
    if not recommendations:
        recommendations.append("Maintain the current production sequence and review actual-versus-plan daily.")

    chart_items = []
    if not actuals.empty and "Order" in actuals and "Attainment %" in actuals:
        values = pd.to_numeric(actuals["Attainment %"], errors="coerce").fillna(0)
        chart_items = [
            (str(actuals.iloc[index]["Order"]), float(value), f"{value:,.1f}% attainment")
            for index, value in enumerate(values.head(10))
        ]

    spec = ExecutiveReportSpec(
        title="Co-Man Production Executive Report",
        subtitle="Production queue, customer commitments, labor, machine capacity, and actual performance.",
        palette=PRODUCTION_PALETTE,
        organization=str(payload.get("organization") or "Current production organization"),
        facility=str(payload.get("facility") or "Current production facility"),
        reporting_period=str(payload.get("reporting_period") or "Current production queue"),
        metrics=[
            ReportMetric("Open Orders", f"{open_orders}", "Active production queue"),
            ReportMetric("Planned Units", f"{planned_units:,.0f}", "Across current orders"),
            ReportMetric("External Jobs", f"{external_jobs}", "Customer-owned work"),
            ReportMetric("Late Jobs", f"{late_jobs}", "Past due and incomplete"),
            ReportMetric("Completed Jobs", f"{completed_jobs}", "Actuals recorded"),
            ReportMetric("Actual Units", f"{actual_units:,.0f}", "Good finished output"),
            ReportMetric("Average Attainment", f"{attainment:,.1f}%", "Actual versus planned"),
            ReportMetric("Actual Labor", f"{labor_hours:,.1f} hr", f"{scrap:,.0f} scrap units"),
        ],
        executive_brief=(
            (
                f"The current Co-Man queue contains {open_orders} open jobs and {planned_units:,.0f} planned units. "
                f"Completed work is averaging {attainment:,.1f}% attainment with {scrap:,.0f} recorded scrap units."
            )
            if has_data
            else "This report was generated without Co-Man operating data; schedule and performance conclusions are not yet available."
        ),
        findings=findings,
        recommendations=recommendations,
        chart_title="Completed Job Attainment",
        chart_items=chart_items,
        sections=[
            ReportSection("Production Queue", orders, "Internal and external production commitments.", max_rows=80),
            ReportSection("Completed Job Performance", actuals, "Output, attainment, scrap, rework, machine hours, and labor.", max_rows=80),
            ReportSection("Facility Machines", machines, "Configured machine capacity and observed operating rates.", max_rows=60),
            ReportSection("Crew Availability", crew, "Scheduled crew capacity available to the production plan.", max_rows=60),
            ReportSection("Customer Portfolio", customers, "External Co-Man customers represented in the current operation.", max_rows=60),
        ],
    )
    return build_executive_pdf(spec)
