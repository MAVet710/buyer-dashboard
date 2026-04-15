import pandas as pd
import streamlit as st

from core.session_keys import BUYER_READY, EXTRACTION_RUNS, INV_RAW, SALES_RAW
from ui.components import render_metric_card, render_section_header


def _safe_len(df) -> int:
    return int(len(df)) if isinstance(df, pd.DataFrame) else 0


def _buyer_summary(detail_product_df: pd.DataFrame, inv_df: pd.DataFrame, sales_df: pd.DataFrame) -> dict:
    if not isinstance(detail_product_df, pd.DataFrame) or detail_product_df.empty:
        return {
            "tracked_products": 0,
            "reorder_now": 0,
            "avg_doh": 0.0,
            "inventory_units": int(pd.to_numeric(inv_df.get("onhandunits", 0), errors="coerce").fillna(0).sum()) if isinstance(inv_df, pd.DataFrame) else 0,
            "sales_rows": _safe_len(sales_df),
            "top_alerts": ["No buyer summary available yet. Prepare buyer data first."],
        }
    doh_series = pd.to_numeric(detail_product_df.get("daysonhand", 0), errors="coerce").fillna(0)
    reorder_now = int((doh_series > 0).mul(doh_series <= 7).sum())
    low_cover = int((doh_series > 0).mul(doh_series <= 21).sum())
    dead_items = int((pd.to_numeric(detail_product_df.get("unitssold", 0), errors="coerce").fillna(0) <= 0).sum())
    alerts = []
    if reorder_now > 0:
        alerts.append(f"{reorder_now} product rows are at 7 days of supply or less.")
    if low_cover > reorder_now:
        alerts.append(f"{low_cover} product rows are at 21 days of supply or less.")
    if dead_items > 0:
        alerts.append(f"{dead_items} product rows have zero sales in the loaded period.")
    if not alerts:
        alerts.append("Buyer inventory health looks stable from the loaded dataset.")
    return {
        "tracked_products": len(detail_product_df),
        "reorder_now": reorder_now,
        "avg_doh": float(doh_series.mean()) if len(doh_series) else 0.0,
        "inventory_units": int(pd.to_numeric(detail_product_df.get("onhandunits", 0), errors="coerce").fillna(0).sum()),
        "sales_rows": _safe_len(sales_df),
        "top_alerts": alerts[:3],
    }


def _extraction_summary(run_df: pd.DataFrame) -> dict:
    if not isinstance(run_df, pd.DataFrame) or run_df.empty:
        return {
            "runs": 0,
            "avg_yield": 0.0,
            "avg_margin": 0.0,
            "active_runs": 0,
            "top_alerts": ["No extraction summary available yet. Load or enter extraction runs first."],
        }
    yield_series = pd.to_numeric(run_df.get("yield_pct", 0), errors="coerce").fillna(0)
    margin_series = pd.to_numeric(run_df.get("gross_margin_pct", 0), errors="coerce").fillna(0)
    active_runs = int((run_df.get("run_status", pd.Series(dtype=str)).astype(str) == "Active").sum())
    qa_holds = int(run_df.get("qa_hold", pd.Series(dtype=bool)).fillna(False).sum())
    low_recovery = int((pd.to_numeric(run_df.get("solvent_recovery_pct", 0), errors="coerce").fillna(0) < 85).sum())
    reprocessed = int(run_df.get("reprocessed", pd.Series(dtype=bool)).fillna(False).sum())
    alerts = []
    if qa_holds > 0:
        alerts.append(f"{qa_holds} extraction run(s) are on QA hold.")
    if low_recovery > 0:
        alerts.append(f"{low_recovery} run(s) are below 85% solvent recovery.")
    if reprocessed > 0:
        alerts.append(f"{reprocessed} run(s) are marked as reprocessed.")
    if not alerts:
        alerts.append("Extraction performance looks stable from the loaded dataset.")
    return {
        "runs": len(run_df),
        "avg_yield": float(yield_series.mean()) if len(yield_series) else 0.0,
        "avg_margin": float(margin_series.mean()) if len(margin_series) else 0.0,
        "active_runs": active_runs,
        "top_alerts": alerts[:3],
    }


def _executive_actions(buyer: dict, extraction: dict) -> list[str]:
    actions = []
    if buyer.get("reorder_now", 0) > 0:
        actions.append("Review critical buyer reorder lines and confirm open-to-buy coverage.")
    if extraction.get("active_runs", 0) > 0:
        actions.append("Check active extraction runs for stage progress and bottlenecks.")
    if extraction.get("avg_margin", 0) < 35 and extraction.get("runs", 0) > 0:
        actions.append("Gross margin is compressed on extraction. Review cost-per-gram and yield-drop trends.")
    if buyer.get("avg_doh", 0) > 90:
        actions.append("Average buyer days on hand is elevated. Review slow movers and markdown exposure.")
    if not actions:
        actions.append("No urgent cross-functional executive actions detected from the loaded data.")
    return actions[:4]


def render_command_center_v2():
    buyer_df = st.session_state.get(BUYER_READY) or st.session_state.get("detail_product_cached_df")
    extraction_df = st.session_state.get(EXTRACTION_RUNS)
    inv_df = st.session_state.get(INV_RAW)
    sales_df = st.session_state.get(SALES_RAW)

    render_section_header(
        "Executive Command Center",
        "Leadership-only rollup. Buyer and extraction stay separate in their own workspaces. Cross-functional visibility lives here only.",
    )

    buyer = _buyer_summary(buyer_df, inv_df, sales_df)
    extraction = _extraction_summary(extraction_df)
    actions = _executive_actions(buyer, extraction)

    top = st.columns(6)
    with top[0]:
        render_metric_card("Buyer Products", f"{buyer['tracked_products']:,}", "Tracked buyer product rows")
    with top[1]:
        render_metric_card("Buyer Reorder Now", f"{buyer['reorder_now']:,}", "Rows at 7 DOH or less")
    with top[2]:
        render_metric_card("Buyer Avg DOH", f"{buyer['avg_doh']:.1f}", "Average buyer days on hand")
    with top[3]:
        render_metric_card("Extraction Runs", f"{extraction['runs']:,}", "Tracked extraction runs")
    with top[4]:
        render_metric_card("Extraction Avg Yield", f"{extraction['avg_yield']:.1f}%", "Average run yield")
    with top[5]:
        render_metric_card("Extraction Avg Margin", f"{extraction['avg_margin']:.1f}%", "Average extraction gross margin")

    buyer_tab, extraction_tab, action_tab = st.tabs([
        "Buyer Summary",
        "Extraction Summary",
        "Executive Actions",
    ])

    with buyer_tab:
        st.markdown("### Buyer Summary")
        for alert in buyer["top_alerts"]:
            st.warning(alert)
        buyer_detail = pd.DataFrame([
            ["Tracked buyer products", buyer["tracked_products"]],
            ["Reorder-now rows", buyer["reorder_now"]],
            ["Average DOH", round(buyer["avg_doh"], 2)],
            ["Inventory units", buyer["inventory_units"]],
            ["Sales rows loaded", buyer["sales_rows"]],
        ], columns=["Metric", "Value"])
        st.dataframe(buyer_detail, use_container_width=True, hide_index=True)

    with extraction_tab:
        st.markdown("### Extraction Summary")
        for alert in extraction["top_alerts"]:
            st.warning(alert)
        extraction_detail = pd.DataFrame([
            ["Tracked runs", extraction["runs"]],
            ["Active runs", extraction["active_runs"]],
            ["Average yield", round(extraction["avg_yield"], 2)],
            ["Average gross margin", round(extraction["avg_margin"], 2)],
        ], columns=["Metric", "Value"])
        st.dataframe(extraction_detail, use_container_width=True, hide_index=True)

    with action_tab:
        st.markdown("### Executive Actions")
        for action in actions:
            st.info(action)
