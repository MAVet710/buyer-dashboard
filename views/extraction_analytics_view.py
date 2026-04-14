import streamlit as st
import pandas as pd

from core.session_keys import EXTRACTION_RUNS
from ui.components import render_metric_card, render_section_header, render_status_pill


def _to_numeric(df: pd.DataFrame, candidates: list[str]) -> pd.Series | None:
    for col in candidates:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce")
    return None


def _status_from_row(row: pd.Series) -> str:
    text = " ".join(str(v).lower() for v in row.values)
    if any(x in text for x in ["fail", "failed", "hold", "reject", "error"]):
        return "At Risk"
    if any(x in text for x in ["pending", "review", "warning"]):
        return "Review"
    return "Healthy"


def render_extraction_analytics_view():
    render_section_header("Extraction Analytics", "Commercial-style analytics workspace for run health, yield, and alert review.")

    run_df = st.session_state.get(EXTRACTION_RUNS)
    if not isinstance(run_df, pd.DataFrame) or run_df.empty:
        st.info("No extraction runs loaded yet. Use Extraction Prep first.")
        return

    df = run_df.copy()
    df["Run Status"] = df.apply(_status_from_row, axis=1)

    yield_series = _to_numeric(df, ["yield", "yield_pct", "yield_percent", "actual_yield_pct"])
    temp_series = _to_numeric(df, ["extraction_temperature_c", "temp_c", "temperature_c"])
    purge_series = _to_numeric(df, ["purge_temperature_c", "purge_temp_c"])

    top = st.columns(4)
    with top[0]:
        render_metric_card("Runs", f"{len(df):,}", "Loaded extraction runs")
    with top[1]:
        render_metric_card("At Risk", f"{(df['Run Status'] == 'At Risk').sum():,}", "Runs with failure or hold signals")
    with top[2]:
        avg_yield = f"{yield_series.mean():.2f}%" if yield_series is not None and yield_series.notna().any() else "N/A"
        render_metric_card("Avg Yield", avg_yield, "Average detected yield field")
    with top[3]:
        avg_temp = f"{temp_series.mean():.1f}°C" if temp_series is not None and temp_series.notna().any() else "N/A"
        render_metric_card("Avg Temp", avg_temp, "Average extraction temperature")

    alert_col, chart_col = st.columns([1, 2])

    with alert_col:
        st.markdown("### Run Alerts")
        risk = int((df["Run Status"] == "At Risk").sum())
        review = int((df["Run Status"] == "Review").sum())
        healthy = int((df["Run Status"] == "Healthy").sum())

        render_status_pill(f"Healthy: {healthy}", "good")
        st.write("")
        render_status_pill(f"Review: {review}", "warn")
        st.write("")
        render_status_pill(f"At Risk: {risk}", "bad")

        if purge_series is not None and purge_series.notna().any() and purge_series.mean() > 38:
            st.warning("Average purge temperature is elevated. Review terpene retention risk.")
        if temp_series is not None and temp_series.notna().any() and temp_series.mean() > 40:
            st.warning("Extraction temperature trend may be too aggressive for terpene preservation.")

    with chart_col:
        st.markdown("### Yield and Process Trends")
        chart_df = pd.DataFrame(index=df.index)
        if yield_series is not None:
            chart_df["Yield %"] = yield_series
        if temp_series is not None:
            chart_df["Extraction Temp C"] = temp_series
        if purge_series is not None:
            chart_df["Purge Temp C"] = purge_series
        if not chart_df.empty:
            st.line_chart(chart_df, use_container_width=True)
        else:
            st.info("No chartable numeric yield/temp fields detected in the uploaded run file yet.")

    st.markdown("### Run Board")
    preview = df.head(200).copy()
    st.dataframe(preview, use_container_width=True, hide_index=True)
