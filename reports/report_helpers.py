from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

import pandas as pd


def frame(value) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if value is None:
        return pd.DataFrame()
    if isinstance(value, Mapping):
        return pd.DataFrame([value])
    try:
        return pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()


def normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def resolve_column(df: pd.DataFrame, *aliases: str) -> str | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    lookup = {normalized_key(column): column for column in df.columns}
    for alias in aliases:
        column = lookup.get(normalized_key(alias))
        if column is not None:
            return str(column)
    return None


def numeric_series(df: pd.DataFrame, *aliases: str, default: float = 0.0) -> pd.Series:
    column = resolve_column(df, *aliases)
    if column is None:
        return pd.Series([default] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def numeric_sum(df: pd.DataFrame, *aliases: str, default: float = 0.0) -> float:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return float(default)
    return float(numeric_series(df, *aliases, default=default).sum())


def numeric_mean(df: pd.DataFrame, *aliases: str, default: float = 0.0) -> float:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return float(default)
    values = numeric_series(df, *aliases, default=default)
    return float(values.mean()) if not values.empty else float(default)


def first_present(mapping: Mapping | None, aliases: Iterable[str], default=None):
    source = mapping if isinstance(mapping, Mapping) else {}
    lookup = {normalized_key(key): value for key, value in source.items()}
    for alias in aliases:
        key = normalized_key(alias)
        if key in lookup and lookup[key] is not None:
            return lookup[key]
    return default


def display_frame(
    df: pd.DataFrame,
    columns: Sequence[tuple[str, Sequence[str]]],
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    output = pd.DataFrame(index=df.index)
    for display_name, aliases in columns:
        column = resolve_column(df, *aliases)
        if column is not None:
            output[display_name] = df[column]
    return output.reset_index(drop=True)


def humanize(value: object) -> str:
    text = re.sub(r"[_\-]+", " ", str(value)).strip()
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return text.title().replace("Sku", "SKU").replace("Coa", "COA").replace("Qa", "QA")
