from __future__ import annotations

import pandas as pd


def _monday_week_start(series: pd.Series) -> pd.Series:
    """Return week buckets anchored to Monday starts."""
    dt = pd.to_datetime(series, errors="coerce")
    return (dt.dt.normalize() - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.date.astype(str)


def build_extraction_weekly_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    """Build weekly executive totals for extraction command center analytics."""
    if run_df is None or run_df.empty:
        return pd.DataFrame()

    df = run_df.copy()
    df["week_start"] = _monday_week_start(df.get("run_date"))
    df["input_weight_g"] = pd.to_numeric(df.get("input_weight_g", 0), errors="coerce").fillna(0)
    df["finished_output_g"] = pd.to_numeric(df.get("finished_output_g", 0), errors="coerce").fillna(0)
    df["yield_pct"] = pd.to_numeric(df.get("yield_pct", 0), errors="coerce").fillna(0)
    df["est_revenue_usd"] = pd.to_numeric(df.get("est_revenue_usd", 0), errors="coerce").fillna(0)
    df["cogs_usd"] = pd.to_numeric(df.get("cogs_usd", 0), errors="coerce").fillna(0)
    df["qa_hold"] = pd.Series(df.get("qa_hold", False)).astype(bool)

    weekly = (
        df.groupby("week_start", dropna=True)
        .agg(
            extraction_runs=("batch_id_internal", "count"),
            input_weight_g=("input_weight_g", "sum"),
            finished_output_g=("finished_output_g", "sum"),
            avg_yield_pct=("yield_pct", "mean"),
            est_revenue_usd=("est_revenue_usd", "sum"),
            cogs_usd=("cogs_usd", "sum"),
            qa_hold_runs=("qa_hold", "sum"),
        )
        .reset_index()
        .sort_values("week_start", ascending=False)
    )
    weekly["gross_margin_pct"] = weekly.apply(
        lambda r: ((r["est_revenue_usd"] - r["cogs_usd"]) / r["est_revenue_usd"] * 100) if r["est_revenue_usd"] else 0.0,
        axis=1,
    )
    return weekly
