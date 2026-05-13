import pandas as pd

from utils.dataframe_helpers import _safe_numeric_mean, _safe_series_mean


def test_safe_numeric_mean_returns_mean_for_numeric_column():
    df = pd.DataFrame({"value": [1, 2, 3, 4]})

    assert _safe_numeric_mean(df, "value", default=0.0) == 2.5


def test_safe_numeric_mean_returns_default_for_missing_column():
    df = pd.DataFrame({"other": [1, 2, 3]})

    assert _safe_numeric_mean(df, "value", default=7.0) == 7.0


def test_safe_numeric_mean_returns_default_for_empty_dataframe():
    df = pd.DataFrame(columns=["value"])

    assert _safe_numeric_mean(df, "value", default=5.0) == 5.0


def test_safe_numeric_mean_handles_non_numeric_values():
    df = pd.DataFrame({"value": ["a", None, "3", "b"]})

    assert _safe_numeric_mean(df, "value", default=0.0) == 0.75


def test_safe_series_mean_handles_normal_series():
    series = pd.Series([1, 2, 3])

    assert _safe_series_mean(series, default=0.0) == 2.0


def test_safe_series_mean_handles_none():
    assert _safe_series_mean(None, default=9.0) == 9.0
