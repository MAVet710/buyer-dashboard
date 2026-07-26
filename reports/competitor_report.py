from __future__ import annotations

import pandas as pd

from reports.executive_system import (
    ExecutiveReportSpec,
    RETAIL_PALETTE,
    ReportMetric,
    ReportSection,
    build_executive_pdf,
)
from reports.report_helpers import frame, numeric_mean


def _build_competitor_intelligence_report_pdf(payload: dict) -> bytes:
    payload = payload or {}
    snapshot = frame(payload.get("competitor_snapshot_df"))
    price = frame(payload.get("price_summary"))
    assortment = frame(payload.get("assortment_summary"))
    promo = frame(payload.get("promo_summary"))
    category_gap = frame(payload.get("category_gap_df"))
    price_gap = frame(payload.get("price_gap_df"))
    opportunity_risk = frame(payload.get("opportunity_risk_df"))
    data_quality = payload.get("data_quality") or {}
    metadata = payload.get("snapshot_metadata") or {}

    competitors = snapshot["competitor_name"].nunique() if "competitor_name" in snapshot else 0
    categories = snapshot["category"].nunique() if "category" in snapshot else 0
    products = len(snapshot)
    avg_price = numeric_mean(snapshot, "effective price", "effective_price")
    discounts = pd.to_numeric(snapshot.get("discount_pct", pd.Series(dtype=float)), errors="coerce").fillna(0)
    promo_count = int((discounts > 0).sum())
    avg_discount = float(discounts[discounts > 0].mean()) if (discounts > 0).any() else 0.0
    review_rows = int(data_quality.get("rows_needing_review") or 0)

    findings = []
    if snapshot.empty:
        findings.append("No competitor snapshot is available for market analysis.")
    if promo_count:
        findings.append(f"{promo_count} captured listings are promoted at an average {avg_discount:,.1f}% discount.")
    if review_rows:
        findings.append(f"{review_rows} captured rows require data-quality review.")
    if not category_gap.empty:
        findings.append("Direct category gaps are available against the internal menu.")
    if not findings:
        findings.append("The current capture contains no material promo or data-quality exceptions.")

    recommendations = list(payload.get("recommendations") or [])
    if snapshot.empty:
        recommendations = ["Capture or upload competitor menus before making market-position decisions."]
    elif not recommendations:
        recommendations = [
            "Review price position and assortment gaps before the next buying cycle.",
            "Refresh competitor captures on a consistent cadence to preserve trend quality.",
        ]

    chart_items = []
    if not snapshot.empty and "category" in snapshot:
        category_counts = snapshot["category"].fillna("Unspecified").astype(str).value_counts().head(10)
        chart_items = [(str(label), float(value), f"{int(value)} products") for label, value in category_counts.items()]

    market_read = str(
        payload.get("market_read_text")
        or (
            f"The captured market contains {products:,} products across {competitors} competitors and {categories} categories."
            if not snapshot.empty
            else "This report was generated without a competitor snapshot; market conclusions are not yet available."
        )
    )
    spec = ExecutiveReportSpec(
        title="Competitor Intelligence Executive Report",
        subtitle="Market pricing, promotional pressure, assortment depth, and menu opportunities.",
        palette=RETAIL_PALETTE,
        organization=str(payload.get("organization") or "Current retail operation"),
        facility=str(metadata.get("location") or metadata.get("market") or "Competitive market"),
        reporting_period=str(metadata.get("snapshot_date") or payload.get("last_processed") or "Current snapshot"),
        metrics=[
            ReportMetric("Competitors", f"{competitors}", "Captured operators"),
            ReportMetric("Products Captured", f"{products:,}", "Parsed menu listings"),
            ReportMetric("Categories", f"{categories}", "Captured categories"),
            ReportMetric("Average Price", f"${avg_price:,.2f}", "Effective menu price"),
            ReportMetric("Promoted Listings", f"{promo_count}", "Listings with a discount"),
            ReportMetric("Average Discount", f"{avg_discount:,.1f}%", "Promoted listings only"),
            ReportMetric("Review Rows", f"{review_rows}", "Data-quality queue"),
            ReportMetric("Files Processed", f"{int(data_quality.get('files_processed') or 0)}", "Current capture"),
        ],
        executive_brief=market_read,
        findings=findings,
        recommendations=recommendations,
        chart_title="Captured Assortment by Category",
        chart_items=chart_items,
        sections=[
            ReportSection("Price Intelligence", price, "Average and effective pricing by market segment.", max_rows=70),
            ReportSection("Assortment Intelligence", assortment, "SKU depth and assortment concentration.", max_rows=70),
            ReportSection("Promo Pressure", promo, "Promotional activity by category and subcategory.", max_rows=70),
            ReportSection("Our Menu vs. Competitors", category_gap, "Internal menu gaps against the captured market.", max_rows=70),
            ReportSection("Price Positioning", price_gap, "Direct internal-versus-market price position.", max_rows=70),
            ReportSection("Opportunity / Risk Matrix", opportunity_risk, "Prioritized commercial opportunities and threats.", max_rows=70),
            ReportSection("Captured Product Sample", snapshot.head(40), "Representative source rows supporting this report.", max_rows=40),
        ],
    )
    return build_executive_pdf(spec)
