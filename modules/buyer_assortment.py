"""Deterministic assortment-level recommendations for the AI Buyer Brief."""

from __future__ import annotations

import math

import pandas as pd


STRAIN_FAMILIES = ("indica", "sativa", "hybrid", "cbd")


def coalesce_duplicate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize and safely merge duplicate export columns.

    POS exports occasionally contain columns that differ only by capitalization
    or whitespace (for example ``Category`` and ``category``). Pandas then
    returns a DataFrame instead of a Series for ``frame["category"]``, which can
    trigger the ambiguous-Series truth-value error in Buyer Intelligence.
    """

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Buyer Intelligence requires a pandas DataFrame.")

    normalized = frame.copy()
    normalized.columns = [str(column).strip().casefold() for column in normalized.columns]
    if not normalized.columns.duplicated().any():
        return normalized

    merged: dict[str, pd.Series] = {}
    for column in dict.fromkeys(normalized.columns):
        matches = normalized.loc[:, normalized.columns == column]
        if matches.shape[1] == 1:
            merged[column] = matches.iloc[:, 0]
            continue
        usable = matches.replace(r"^\s*$", pd.NA, regex=True)
        merged[column] = usable.bfill(axis=1).iloc[:, 0]
    return pd.DataFrame(merged, index=normalized.index)


def _strain_family(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    return next((family for family in STRAIN_FAMILIES if family in normalized), "unspecified")


def _assortment_label(category: object, strain_type: object, package_size: object) -> str:
    category_text = str(category or "product").strip().casefold()
    strain_text = str(strain_type or "").strip().casefold()
    size_text = str(package_size or "").strip().casefold()
    family = _strain_family(strain_text)

    if "vape" in category_text:
        product = "Disposable Vape" if "disposable" in strain_text else "Vape"
    elif "pre roll" in category_text or "preroll" in category_text:
        product = "Infused Pre-Roll" if "infused" in strain_text else "Pre-Roll"
    elif "flower" in category_text:
        product = "Flower"
    elif "edible" in category_text:
        product = "Edible"
    elif "beverage" in category_text:
        product = "Beverage"
    elif "concentrate" in category_text:
        product = "Concentrate"
    else:
        product = str(category or "Product").strip().title()

    parts = []
    if size_text and size_text != "unspecified":
        parts.append(size_text)
    if family != "unspecified":
        parts.append(family.title())
    else:
        parts.append("Any-Strain")
    parts.append(product)
    return " ".join(parts)


def build_assortment_priorities(
    by_product: pd.DataFrame,
    *,
    target_cover_days: int = 28,
    max_rows: int = 12,
) -> pd.DataFrame:
    """Roll SKU risk into buyer-ready category/strain/size recommendations."""

    output_columns = [
        "Need",
        "Recommended units",
        "Current on hand",
        "Days of cover",
        "Units sold",
        "SKUs",
        "Reason",
    ]
    if not isinstance(by_product, pd.DataFrame) or by_product.empty:
        return pd.DataFrame(columns=output_columns)

    required = {
        "category",
        "strain_type",
        "package_size",
        "avg_daily_units",
        "on_hand_units",
        "units_sold",
    }
    if not required.issubset(by_product.columns):
        return pd.DataFrame(columns=output_columns)

    frame = by_product.copy()
    for column in ("category", "strain_type", "package_size"):
        frame[column] = frame[column].fillna("unspecified").astype(str).str.strip()
    frame["avg_daily_units"] = pd.to_numeric(
        frame["avg_daily_units"], errors="coerce"
    ).fillna(0.0).clip(lower=0)
    frame["units_sold"] = pd.to_numeric(
        frame["units_sold"], errors="coerce"
    ).fillna(0.0).clip(lower=0)
    frame["on_hand_units"] = pd.to_numeric(
        frame["on_hand_units"], errors="coerce"
    )
    frame = frame[
        (frame["avg_daily_units"] > 0) & frame["on_hand_units"].notna()
    ].copy()
    frame["on_hand_units"] = frame["on_hand_units"].clip(lower=0)
    if frame.empty:
        return pd.DataFrame(columns=output_columns)

    grouped = (
        frame.groupby(["category", "strain_type", "package_size"], dropna=False)
        .agg(
            avg_daily_units=("avg_daily_units", "sum"),
            on_hand_units=("on_hand_units", "sum"),
            units_sold=("units_sold", "sum"),
            sku_count=("product_name", "nunique") if "product_name" in frame.columns else ("category", "size"),
        )
        .reset_index()
    )
    grouped["days_of_cover"] = grouped["on_hand_units"] / grouped["avg_daily_units"]
    grouped["recommended_units"] = (
        grouped["avg_daily_units"] * max(1, int(target_cover_days))
        - grouped["on_hand_units"]
    ).clip(lower=0).map(math.ceil)
    grouped = grouped[grouped["recommended_units"] > 0].copy()
    if grouped.empty:
        return pd.DataFrame(columns=output_columns)

    grouped["Need"] = grouped.apply(
        lambda row: _assortment_label(
            row["category"], row["strain_type"], row["package_size"]
        ),
        axis=1,
    )
    grouped["Recommended units"] = grouped["recommended_units"].astype(int)
    grouped["Current on hand"] = grouped["on_hand_units"].round(1)
    grouped["Days of cover"] = grouped["days_of_cover"].round(1)
    grouped["Units sold"] = grouped["units_sold"].round(0).astype(int)
    grouped["SKUs"] = grouped["sku_count"].astype(int)
    grouped["Reason"] = grouped.apply(
        lambda row: (
            f"{row['days_of_cover']:.1f} days of cover; "
            f"{int(round(row['units_sold']))} units sold in the selected window"
        ),
        axis=1,
    )
    return (
        grouped.sort_values(
            ["recommended_units", "avg_daily_units", "days_of_cover"],
            ascending=[False, False, True],
        )
        .head(max(1, int(max_rows)))[output_columns]
        .reset_index(drop=True)
    )
