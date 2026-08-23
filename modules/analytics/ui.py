"""Profitability analytics dashboard for vertical cannabis operations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine
from modules.design.responsive import responsive_columns, is_mobile
from modules.extraction.repository import ExtractionRepository
from modules.production_erp.service import ProductionERPService

from .service import ProfitabilityAnalyticsService


def render_analytics_dashboard(state: dict[str, Any]) -> None:
    """Render profitability analytics for entire supply chain."""
    org_id = str(state.get("active_organization_id") or "")
    facility_id = str(state.get("active_facility_id") or "")

    if not org_id or not facility_id:
        st.info("Select an organization and facility to see analytics.")
        return

    st.markdown("# 📊 Profitability Analytics")
    st.caption("Margin tracking across cultivation → processing → extraction → retail supply chain.")

    try:
        analytics = ProfitabilityAnalyticsService(create_coman_engine())
        extraction = ExtractionRepository(create_coman_engine())
    except Exception as e:
        st.error(f"Failed to connect to analytics engine: {str(e)}")
        return

    # Time period selector
    col1, col2 = st.columns([2, 1])
    with col1:
        period_days = st.slider("Analysis period (days)", 7, 365, 30, step=7)
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # ===========================================================================
    # SECTION 1: SUPPLY CHAIN MARGIN OVERVIEW
    # ===========================================================================
    st.markdown("## 💰 Supply Chain Margin")

    try:
        margin_data = analytics.supply_chain_margin(org_id, facility_id, period_days)

        cols = responsive_columns(4)
        with cols[0]:
            st.metric("Total Revenue", f"${margin_data['total_revenue']:,.0f}")
        with cols[1 % len(cols)]:
            st.metric("Total COGS", f"${margin_data['total_cogs']:,.0f}")
        with cols[2 % len(cols)]:
            st.metric("Gross Margin", f"${margin_data['gross_margin']:,.0f}")
        with cols[3 % len(cols)]:
            st.metric(
                "Margin %",
                f"{margin_data['gross_margin_pct']:.1f}%",
                delta=f"Target: 45%" if margin_data['gross_margin_pct'] < 45 else None,
            )

        st.caption(f"Period: Last {period_days} days")

    except Exception as e:
        st.error(f"Supply chain margin error: {str(e)}")

    # ===========================================================================
    # SECTION 2: PRODUCT PROFITABILITY
    # ===========================================================================
    st.markdown("## 📦 Product Profitability")

    try:
        products = analytics.product_profitability(org_id, facility_id, period_days)

        if products:
            df_products = pd.DataFrame(products)

            # Format for display
            display_df = df_products[[
                "product_name",
                "sku",
                "units_sold",
                "revenue",
                "cogs",
                "margin",
                "margin_pct",
            ]].copy()

            display_df.columns = [
                "Product",
                "SKU",
                "Units Sold",
                "Revenue",
                "COGS",
                "Margin",
                "Margin %",
            ]

            # Color code margin %
            st.dataframe(
                display_df.style.format({
                    "Units Sold": "{:,.2f}",
                    "Revenue": "${:,.0f}",
                    "COGS": "${:,.0f}",
                    "Margin": "${:,.0f}",
                    "Margin %": "{:.1f}%",
                }).background_gradient(subset=["Margin %"], cmap="RdYlGn", vmin=0, vmax=60),
                use_container_width=True,
                hide_index=True,
            )

            # Top products summary
            top_revenue = df_products.nlargest(3, "revenue")
            top_margin = df_products.nlargest(3, "margin_pct")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Top by Revenue**")
                for idx, row in top_revenue.iterrows():
                    st.caption(f"🔹 {row['product_name']}: ${row['revenue']:,.0f}")

            with col2:
                st.markdown("**Top by Margin %**")
                for idx, row in top_margin.iterrows():
                    st.caption(f"✅ {row['product_name']}: {row['margin_pct']:.1f}%")

        else:
            st.info("No product sales in this period.")

    except Exception as e:
        st.error(f"Product profitability error: {str(e)}")

    # ===========================================================================
    # SECTION 3: PRODUCTION COST BREAKDOWN
    # ===========================================================================
    st.markdown("## 🏭 Production Costs")

    try:
        production = ProductionERPService(create_coman_engine())
        prod_data = analytics.production_cost_analysis(org_id, facility_id, period_days)

        if prod_data["breakdown"]:
            if is_mobile():
                st.metric("Total Production Cost", f"${prod_data['total_production_cost']:,.0f}")
            else:
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.metric("Total Production Cost", f"${prod_data['total_production_cost']:,.0f}")

            with col2:
                # Cost breakdown pie chart
                breakdown = prod_data["breakdown"]
                chart_data = {
                    k: v["total_usd"] for k, v in breakdown.items() if v["total_usd"] > 0
                }

                if chart_data:
                    import plotly.graph_objects as go
                    fig = go.Figure(data=[go.Pie(
                        labels=list(chart_data.keys()),
                        values=list(chart_data.values()),
                        hole=0.3,
                    )])
                    fig.update_layout(
                        height=300,
                        margin=dict(l=0, r=0, t=0, b=0),
                        showlegend=True,
                    )
                    st.plotly_chart(fig, use_container_width=True)

            # Detailed breakdown table
            st.caption("**Cost Details**")
            breakdown_df = pd.DataFrame([
                {
                    "Category": cat,
                    "Total": f"${data['total_usd']:,.0f}",
                    "Events": data["events"],
                }
                for cat, data in breakdown.items()
            ])
            st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

        else:
            st.info("No production costs recorded in this period.")

    except Exception as e:
        st.error(f"Production cost error: {str(e)}")

    # ===========================================================================
    # SECTION 4: EXTRACTION EFFICIENCY
    # ===========================================================================
    st.markdown("## 🧪 Extraction Efficiency")

    try:
        extraction_data = analytics.extraction_efficiency(org_id, facility_id, period_days)

        if extraction_data["completed_runs"] > 0:
            cols = responsive_columns(4)
            with cols[0]:
                st.metric("Completed Runs", extraction_data["completed_runs"])
            with cols[1 % len(cols)]:
                st.metric("Avg Yield %", f"{extraction_data['avg_yield_pct']:.1f}%")
            with cols[2 % len(cols)]:
                st.metric("Best Yield %", f"{extraction_data['best_yield_pct']:.1f}%")
            with cols[3 % len(cols)]:
                st.metric("Avg Cost/Unit", f"${extraction_data['avg_cost_per_output_unit']:.2f}")

            # Yield range indicator
            if extraction_data["avg_yield_pct"] > 70:
                yield_status = "✅ Excellent"
            elif extraction_data["avg_yield_pct"] > 60:
                yield_status = "🟡 Good"
            else:
                yield_status = "⚠️ Review needed"

            st.caption(f"Yield performance: {yield_status}")

        else:
            st.info("No completed extraction runs in this period.")

    except Exception as e:
        st.error(f"Extraction efficiency error: {str(e)}")

    # ===========================================================================
    # FOOTER: Insights & Recommendations
    # ===========================================================================
    st.markdown("---")
    st.markdown("### 💡 Insights")

    try:
        margin_data = analytics.supply_chain_margin(org_id, facility_id, period_days)

        insights = []

        if margin_data["gross_margin_pct"] < 30:
            insights.append("⚠️ Margin is below 30% — review pricing or cost structure")
        elif margin_data["gross_margin_pct"] > 50:
            insights.append("✅ Strong margin performance — continue current strategy")

        products = analytics.product_profitability(org_id, facility_id, period_days)
        if products:
            losers = [p for p in products if p["margin_pct"] < 0]
            if losers:
                insights.append(f"📊 {len(losers)} product(s) with negative margin — review pricing")

        extraction_data = analytics.extraction_efficiency(org_id, facility_id, period_days)
        if extraction_data["completed_runs"] > 0 and extraction_data["avg_yield_pct"] < 65:
            insights.append("🧪 Extraction yield below benchmark (65%) — review process parameters")

        if insights:
            for insight in insights:
                st.caption(insight)
        else:
            st.caption("✅ Operations within normal parameters")

    except Exception as e:
        st.warning(f"Insights generation error: {str(e)}")
