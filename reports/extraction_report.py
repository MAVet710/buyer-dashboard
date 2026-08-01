from __future__ import annotations

import pandas as pd

from reports.executive_system import (
    ExecutiveReportSpec,
    PRODUCTION_PALETTE,
    ReportMetric,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import display_frame, first_present, frame, numeric_mean, numeric_sum


def _build_extraction_executive_report_pdf(payload: dict) -> bytes:
    payload = payload or {}
    summary = payload.get("summary") or {}
    kpis = payload.get("kpis") or {}
    runs = frame(payload.get("run_performance"))
    if runs.empty:
        runs = frame(payload.get("process_tracking"))
    profitability = frame(payload.get("profitability"))
    inventory = frame(payload.get("extraction_inventory"))

    total_runs = int(first_present(kpis, ["total_runs"], len(runs)))
    input_weight = float(first_present(kpis, ["total_input_weight_g"], numeric_sum(runs, "input weight g", "input_weight_g")))
    output_weight = float(
        first_present(kpis, ["total_finished_output_g"], numeric_sum(runs, "final output g", "finished output g"))
    )
    avg_yield = float(first_present(kpis, ["avg_yield_pct"], numeric_mean(runs, "yield pct", "yield")))
    avg_efficiency = float(first_present(kpis, ["avg_efficiency_pct"], numeric_mean(runs, "efficiency pct", "efficiency")))
    revenue = float(first_present(kpis, ["total_estimated_revenue_usd"], numeric_sum(profitability, "estimated revenue usd", "revenue")))
    cogs = float(first_present(kpis, ["total_cogs_usd"], numeric_sum(profitability, "total cogs usd", "cogs")))
    profit = float(first_present(kpis, ["gross_profit_usd"], numeric_sum(profitability, "gross profit usd", "gross profit")))
    margin = float(first_present(kpis, ["gross_margin_pct"], numeric_mean(profitability, "gross margin pct", "gross margin")))
    at_risk = int(first_present(kpis, ["at_risk_batches"], 0))
    qa_holds = int(first_present(kpis, ["qa_holds_or_coa_pending"], 0))

    has_data = not runs.empty or not profitability.empty or not inventory.empty
    findings = []
    if not has_data:
        findings.append("No extraction run, inventory, or profitability data is available.")
    if qa_holds:
        findings.append(f"{qa_holds} runs are on QA hold or waiting for a COA.")
    if at_risk:
        findings.append(f"{at_risk} batches carry a warning or critical value-risk signal.")
    if total_runs and avg_yield <= 0:
        findings.append("Yield data is incomplete for the current run set.")
    if not findings:
        findings.append("No material production or QA exceptions were detected.")

    recommendations = []
    if not has_data:
        recommendations.append("Upload or enter extraction runs before using this report for production decisions.")
    if qa_holds:
        recommendations.append("Clear QA and COA exceptions before scheduling downstream unitization.")
    if at_risk:
        recommendations.append("Review value-risk batches with production and finance before release.")
    if avg_efficiency and avg_efficiency < 85:
        recommendations.append("Investigate cycle-time loss and equipment constraints below the efficiency target.")
    if not recommendations:
        recommendations.append("Maintain the current run controls and review yield variance after each batch.")

    run_display = display_frame(
        runs,
        [
            ("Run", ["run id", "batch id", "run number"]),
            (
                "Product Name",
                [
                    "product name",
                    "product_name",
                    "finished product",
                    "finished_product",
                    "final product type",
                    "final_product_type",
                    "downstream product",
                    "product type",
                ],
            ),
            ("Method", ["method", "extraction method"]),
            ("Material", ["material", "input material", "strain"]),
            ("Input Weight g", ["input weight g", "input_weight_g"]),
            ("Finished Output g", ["final output g", "finished output g", "final_output_g"]),
            ("Yield %", ["yield pct", "yield %", "yield"]),
            ("Efficiency %", ["efficiency pct", "efficiency %", "efficiency"]),
            ("QA Hold", ["qa hold", "qa_hold"]),
            ("COA Status", ["coa status", "coa_status"]),
        ],
    )
    profitability_display = display_frame(
        profitability,
        [
            ("Run", ["run id", "batch id", "run number"]),
            (
                "Product Name",
                ["product name", "product_name", "finished product", "finished_product", "product"],
            ),
            ("Revenue", ["estimated revenue usd", "revenue"]),
            ("COGS", ["total cogs usd", "cogs"]),
            ("Gross Profit", ["gross profit usd", "gross profit"]),
            ("Gross Margin %", ["gross margin pct", "gross margin"]),
            ("Value Risk", ["value risk flag", "risk"]),
        ],
    )
    inventory_display = display_frame(
        inventory,
        [
            ("Lot", ["lot", "lot id", "package id"]),
            (
                "Product Name",
                ["product name", "product_name", "source product", "source_product", "material name"],
            ),
            ("Material", ["material", "material type"]),
            ("Strain", ["strain"]),
            ("Current Weight g", ["current weight g", "weight g", "current weight"]),
            ("Reserved Weight g", ["reserved weight g", "reserved weight"]),
            ("Available Weight g", ["available weight g", "available weight"]),
            ("Status", ["status", "qa status"]),
        ],
    )
    chart_items = []
    if not run_display.empty and "Run" in run_display and "Yield %" in run_display:
        values = pd.to_numeric(run_display["Yield %"], errors="coerce").fillna(0)
        chart_items = [
            (str(run_display.iloc[index]["Run"] or f"Run {index + 1}"), float(value), f"{value:,.1f}% yield")
            for index, value in enumerate(values.head(10))
        ]

    insights = payload.get("insights") or {}
    brief = str(
        insights.get("summary_of_findings")
        or (
            f"{total_runs} extraction runs processed {input_weight:,.0f} g into {output_weight:,.0f} g "
            f"of finished output at {avg_yield:,.1f}% average yield."
            if has_data
            else "This report was generated without extraction operating data; production conclusions are not yet available."
        )
    )
    spec = ExecutiveReportSpec(
        title="Extraction Operations Executive Report",
        subtitle="Yield, efficiency, value creation, inventory pressure, and QA readiness.",
        palette=PRODUCTION_PALETTE,
        organization=str(summary.get("organization") or "Current production operation"),
        facility=str(summary.get("facility_context") or "Extraction facility"),
        reporting_period=str(summary.get("reporting_period") or "Current session"),
        metrics=[
            ReportMetric("Extraction Runs", f"{total_runs}", "Analyzed production runs"),
            ReportMetric("Input Weight", f"{input_weight:,.0f} g", "Material processed"),
            ReportMetric("Finished Output", f"{output_weight:,.0f} g", "Recovered output"),
            ReportMetric("Average Yield", f"{avg_yield:,.1f}%", "Across analyzed runs"),
            ReportMetric("Average Efficiency", f"{avg_efficiency:,.1f}%", "Operational efficiency"),
            ReportMetric("Estimated Revenue", f"${revenue:,.0f}", "Current run valuation"),
            ReportMetric("Gross Profit", f"${profit:,.0f}", f"{margin:,.1f}% gross margin"),
            ReportMetric("QA / Value Risk", f"{qa_holds + at_risk}", "Open exception signals"),
        ],
        executive_brief=brief,
        findings=findings,
        recommendations=recommendations,
        chart_title="Yield by Extraction Run",
        chart_items=chart_items,
        sections=[
            ReportSection("Run Performance", run_display, "Yield, efficiency, and release status by run.", max_rows=70),
            ReportSection("Run Economics", profitability_display, "Revenue, cost, and gross-profit performance by run.", max_rows=70),
            ReportSection("Source Inventory", inventory_display, "Available, reserved, and status-controlled source material.", max_rows=70),
        ],
    )
    return build_executive_pdf(spec)
