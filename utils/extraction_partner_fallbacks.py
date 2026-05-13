"""Fallback helpers for extraction partner uploads."""

import pandas as pd


def _partner_norm_col(name: str) -> str:
    return "".join(ch.lower() for ch in str(name or "") if ch.isalnum())


def _partner_pick(df: pd.DataFrame, candidates: list[str]) -> str | None:
    norm_to_actual = {_partner_norm_col(c): c for c in df.columns}
    for cand in candidates:
        actual = norm_to_actual.get(_partner_norm_col(cand))
        if actual:
            return actual
    return None


def load_partner_file(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    name = str(getattr(uploaded_file, "name", "")).lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)


def looks_like_partner_extraction_file(uploaded_file) -> bool:
    try:
        df = load_partner_file(uploaded_file)
    except Exception:
        return False
    if df.empty:
        return False
    required_groups = [["strain", "strain_name"], ["wet", "wet_weight"], ["date", "run_date"]]
    for group in required_groups:
        if _partner_pick(df, group):
            continue
        return False
    return True


def map_partner_runs_to_ecc_shape(df: pd.DataFrame) -> pd.DataFrame:
    return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()


def build_extraction_weekly_summary(run_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(run_df, pd.DataFrame) or run_df.empty:
        return pd.DataFrame()
    df = run_df.copy()
    date_col = _partner_pick(df, ["run_date", "date"])
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df["week"] = df[date_col].dt.to_period("W").astype(str)
        return df.groupby("week", dropna=False).size().reset_index(name="runs")
    return pd.DataFrame()
