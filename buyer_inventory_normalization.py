from __future__ import annotations

from typing import Callable, Iterable

import pandas as pd

DEFAULT_ITEMNAME_SOURCE_ALIASES = [
    "itemname", "product_name", "name", "product", "sku_name", "item", "sku", "title", "skuname",
]


def fill_blank_with(series: pd.Series, fallback: pd.Series | str) -> pd.Series:
    out = series.copy()
    invalid = out.isna() | out.astype(str).str.strip().isin(["", "nan", "none", "unknown", "unspecified"])
    if isinstance(fallback, pd.Series):
        out.loc[invalid] = fallback.loc[invalid]
    else:
        out.loc[invalid] = fallback
    return out


def resolve_itemname_series(
    inv_df: pd.DataFrame,
    detected_name_col: str | None,
    detect_column: Callable[[Iterable[str], list[str]], str | None],
    normalize_col: Callable[[str], str],
    itemname_aliases: list[str] | None = None,
) -> pd.Series:
    if detected_name_col and detected_name_col in inv_df.columns:
        series = inv_df[detected_name_col]
    else:
        aliases = itemname_aliases or DEFAULT_ITEMNAME_SOURCE_ALIASES
        source_col = detect_column(inv_df.columns, [normalize_col(a) for a in aliases])
        series = inv_df[source_col] if source_col else pd.Series(["unknown item"] * len(inv_df), index=inv_df.index)
    return series.astype(str).str.strip()


def ensure_inventory_derived_fields(
    inv_df: pd.DataFrame,
    *,
    normalize_category: Callable[[str], str],
    extract_strain_type: Callable[[str, str], str],
    extract_size: Callable[[str, str], str],
    valid_strain_types: set[str] | frozenset[str],
    detect_column: Callable[[Iterable[str], list[str]], str | None],
    normalize_col: Callable[[str], str],
    detected_name_col: str = "itemname",
    itemname_aliases: list[str] | None = None,
) -> pd.DataFrame:
    out = inv_df.copy()
    out["itemname"] = resolve_itemname_series(
        out,
        detected_name_col,
        detect_column=detect_column,
        normalize_col=normalize_col,
        itemname_aliases=itemname_aliases,
    )

    if "subcategory" not in out.columns:
        out["subcategory"] = out["itemname"]
    out["subcategory"] = out["subcategory"].apply(normalize_category)
    inferred_subcategory = out["itemname"].apply(normalize_category)
    out["subcategory"] = fill_blank_with(out["subcategory"], inferred_subcategory).fillna("unspecified")
    out["subcategory"] = out["subcategory"].replace("unknown", "unspecified")

    out["strain_type"] = out.apply(
        lambda x: extract_strain_type(x.get("itemname", ""), x.get("subcategory", "")),
        axis=1,
    )
    if "_explicit_strain_type" in out.columns:
        explicit = out["_explicit_strain_type"].astype(str).str.strip().str.lower()
        valid = explicit.isin(valid_strain_types)
        out.loc[valid, "strain_type"] = explicit[valid]
        out = out.drop(columns=["_explicit_strain_type"])
    out["strain_type"] = fill_blank_with(out["strain_type"], "unspecified")

    out["packagesize"] = out.apply(
        lambda x: extract_size(x.get("itemname", ""), x.get("subcategory", "")),
        axis=1,
    )
    out["packagesize"] = fill_blank_with(out["packagesize"], "unknown")
    out["packagesize"] = out["packagesize"].replace("unspecified", "unknown")

    return out
