import numpy as np
import pandas as pd

def _safe_report_df(value, empty_message="No data available") -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()

    if value is None:
        return pd.DataFrame([{"Message": empty_message}])

    if isinstance(value, list):
        if not value:
            return pd.DataFrame([{"Message": empty_message}])
        try:
            df = pd.DataFrame(value)
            return df if not df.empty else pd.DataFrame([{"Message": empty_message}])
        except Exception:
            return pd.DataFrame([{"Message": empty_message}])

    if isinstance(value, dict):
        if not value:
            return pd.DataFrame([{"Message": empty_message}])
        try:
            if all(not isinstance(v, (dict, list, tuple, set, pd.Series, pd.DataFrame)) for v in value.values()):
                return pd.DataFrame(
                    [{"Metric": str(k), "Value": "" if v is None else str(v)} for k, v in value.items()]
                )
            return pd.DataFrame(
                [{"Metric": str(k), "Value": "" if v is None else str(v)} for k, v in value.items()]
            )
        except Exception:
            return pd.DataFrame([{"Message": empty_message}])

    return pd.DataFrame([{"Value": str(value)}])

def _safe_numeric_series(df, column_name, default=0.0) -> pd.Series:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.Series(dtype="float64")

    if column_name in df.columns:
        return pd.to_numeric(df[column_name], errors="coerce").fillna(default)

    return pd.Series([default] * len(df), index=df.index, dtype="float64")

def _safe_numeric_sum(df, column_name, default=0.0) -> float:
    series = _safe_numeric_series(df, column_name, default=0.0)
    if series.empty:
        return float(default)
    total = series.sum()
    return float(total) if pd.notna(total) else float(default)

def _safe_numeric_mean(df, column_name, default=0.0) -> float:
    return _safe_series_mean(_safe_numeric_series(df, column_name, default=0.0), default=default)
