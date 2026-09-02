from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from time import monotonic
from typing import Any, Iterable

import pandas as pd

from .ma_ccc import MassachusettsCCCProvider, MarketDataset


_CATEGORY_ALIASES = {
    "buds": "Flower",
    "flower": "Flower",
    "usable marijuana": "Flower",
    "raw pre-rolls": "Pre-Rolls",
    "raw pre-roll": "Pre-Rolls",
    "pre-roll": "Pre-Rolls",
    "pre-rolls": "Pre-Rolls",
    "preroll": "Pre-Rolls",
    "prerolls": "Pre-Rolls",
    "infused pre-roll": "Infused Pre-Rolls",
    "infused pre-rolls": "Infused Pre-Rolls",
    "vape product": "Vapes",
    "vape products": "Vapes",
    "vape": "Vapes",
    "vapes": "Vapes",
    "concentrate": "Concentrates",
    "concentrates": "Concentrates",
    "edible": "Edibles",
    "edibles": "Edibles",
    "beverage": "Beverages",
    "beverages": "Beverages",
    "tincture": "Tinctures",
    "tinctures": "Tinctures",
    "topical": "Topicals",
    "topicals": "Topicals",
}

_DATE_KEYS = ("SaleDate", "SalesDate", "Date", "date", "sale_date", "sales_date", "TransactionDate")
_CATEGORY_KEYS = ("ProductCategory", "ProductType", "Category", "category", "product_category", "product_type")
_SALES_KEYS = ("GrossSales", "GrossSalesTotal", "Sales", "TotalSales", "sales", "gross_sales", "gross_sales_total")
_UNITS_KEYS = ("Quantity", "Units", "UnitsSold", "UnitCount", "quantity", "units", "units_sold")
_UPDATED_KEYS = ("CCCLastUpdated", "LastUpdated", "last_updated", "updated_at")
_CACHE_TTL_SECONDS = 6 * 60 * 60
_DATASET_CACHE: dict[tuple[type, str], tuple[float, MarketDataset]] = {}


def _pick(row: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    folded = {str(key).casefold(): value for key, value in row.items()}
    for key in keys:
        value = folded.get(key.casefold())
        if value not in (None, ""):
            return value
    return None


def _pick_fuzzy(row: dict[str, Any], keys: Iterable[str], required_tokens: tuple[str, ...]) -> Any:
    exact = _pick(row, keys)
    if exact not in (None, ""):
        return exact
    for key, value in row.items():
        normalized = str(key).casefold().replace("_", "").replace(" ", "")
        if all(token in normalized for token in required_tokens) and value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def normalize_category(value: Any) -> str:
    raw = str(value or "Unknown").strip()
    folded = raw.casefold()
    if folded in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[folded]
    for alias, normalized in _CATEGORY_ALIASES.items():
        if alias in folded:
            return normalized
    return raw.title() if raw else "Unknown"


def _fetch_cached(provider: MassachusettsCCCProvider, kind: str) -> MarketDataset:
    key = (type(provider), kind)
    cached = _DATASET_CACHE.get(key)
    now = monotonic()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    dataset = provider.fetch_sales() if kind == "sales" else provider.fetch_prices()
    _DATASET_CACHE[key] = (now, dataset)
    return dataset


def _window_growth(points: list[tuple[date, float]], lookback_days: int) -> float | None:
    if not points:
        return None
    latest = max(day for day, _ in points)
    current_start = latest - timedelta(days=lookback_days - 1)
    previous_start = current_start - timedelta(days=lookback_days)
    current = sum(value for day, value in points if current_start <= day <= latest)
    previous = sum(value for day, value in points if previous_start <= day < current_start)
    if previous <= 0:
        return None
    return (current - previous) / previous


def _price_summary(dataset: MarketDataset) -> dict[str, Any]:
    rows: list[tuple[date, float, str | None]] = []
    for row in dataset.rows:
        month = _date(_pick_fuzzy(row, ("YearMonth", "year_month", "Month", "month"), ("month",)))
        value = _number(
            _pick_fuzzy(
                row,
                ("AverageRetailPriceperGm", "AverageRetailPricePerGram", "price_per_gram"),
                ("price", "gm"),
            )
        )
        if month and value > 0:
            rows.append((month, value, _pick(row, _UPDATED_KEYS)))
    rows.sort(key=lambda item: item[0])
    if not rows:
        return {"current_per_gram": None, "change": None, "as_of": None}
    current = rows[-1]
    prior = rows[-2] if len(rows) > 1 else None
    change = ((current[1] - prior[1]) / prior[1]) if prior and prior[1] else None
    return {
        "current_per_gram": round(current[1], 2),
        "change": change,
        "as_of": current[0].isoformat(),
        "source_updated_at": current[2],
    }


def _sales_summary(dataset: MarketDataset, lookback_days: int) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    statewide: list[tuple[date, float]] = []
    by_category: dict[str, list[tuple[date, float]]] = defaultdict(list)
    updated_at: str | None = None
    latest_date: date | None = None

    for row in dataset.rows:
        day = _date(_pick_fuzzy(row, _DATE_KEYS, ("date",)))
        if not day:
            continue
        sales = _number(_pick_fuzzy(row, _SALES_KEYS, ("sales",)))
        units = _number(_pick_fuzzy(row, _UNITS_KEYS, ("unit",)))
        value = sales if sales > 0 else units
        if value <= 0:
            continue
        category_value = _pick(row, _CATEGORY_KEYS)
        if category_value in (None, ""):
            category_value = _pick_fuzzy(row, _CATEGORY_KEYS, ("product", "type"))
        category = normalize_category(category_value)
        statewide.append((day, value))
        by_category[category].append((day, value))
        latest_date = day if latest_date is None or day > latest_date else latest_date
        updated_at = str(_pick(row, _UPDATED_KEYS) or updated_at or "") or None

    market_categories = {
        category: {"category": category, "market_growth": _window_growth(points, lookback_days)}
        for category, points in by_category.items()
        if category != "Unknown"
    }
    return (
        {
            "market_growth": _window_growth(statewide, lookback_days),
            "as_of": latest_date.isoformat() if latest_date else None,
            "source_updated_at": updated_at,
        },
        market_categories,
    )


def _store_categories(store_rows: list[dict[str, Any]], lookback_days: int) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"units": 0.0, "revenue": 0.0})
    for row in store_rows:
        category = normalize_category(row.get("category") or row.get("subcategory") or row.get("mastercategory"))
        totals[category]["units"] += _number(row.get("units_sold") or row.get("unitssold"))
        totals[category]["revenue"] += _number(row.get("revenue") or row.get("net_sales"))
    return {
        category: {
            "category": category,
            "store_units_sold": values["units"],
            "store_revenue": values["revenue"],
            "store_daily_units": values["units"] / max(lookback_days, 1),
        }
        for category, values in totals.items()
    }


def _signal(*, market_growth: float | None, days_of_cover: float | None, target_doh: int = 21) -> str:
    if days_of_cover is None:
        return "MONITOR"
    if days_of_cover <= target_doh and market_growth is not None and market_growth >= 0:
        return "BUY"
    if days_of_cover >= target_doh * 1.5:
        return "HOLD" if market_growth is None or market_growth >= 0 else "REDUCE"
    if market_growth is not None and market_growth < -0.05 and days_of_cover > target_doh:
        return "REDUCE"
    return "MONITOR"


def _category_days_of_cover(product_rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in product_rows:
        category = normalize_category(row.get("category") or row.get("subcategory") or row.get("mastercategory"))
        raw = row.get("days_of_cover")
        if raw in (None, ""):
            raw = row.get("days_of_supply")
        if raw in (None, ""):
            raw = row.get("daysonhand")
        value = _number(raw)
        if value > 0 and value < 9999:
            grouped[category].append(value)
    return {category: sum(values) / len(values) for category, values in grouped.items() if values}


def build_market_intelligence(
    *,
    store_category_rows: list[dict[str, Any]],
    store_product_rows: list[dict[str, Any]],
    lookback_days: int,
    provider: MassachusettsCCCProvider | None = None,
) -> dict[str, Any]:
    provider = provider or MassachusettsCCCProvider()
    try:
        sales_dataset = _fetch_cached(provider, "sales")
        price_dataset = _fetch_cached(provider, "prices")
        statewide, market_categories = _sales_summary(sales_dataset, lookback_days)
        price = _price_summary(price_dataset)
    except Exception as exc:
        return {
            "status": "unavailable",
            "state": provider.state,
            "source": provider.source_name,
            "message": "Market data is temporarily unavailable. Store-level Buyer Intelligence is unaffected.",
            "error_type": type(exc).__name__,
            "categories": [],
        }

    store = _store_categories(store_category_rows, lookback_days)
    cover = _category_days_of_cover(store_product_rows)
    categories = []
    for category in sorted(set(store) | set(market_categories)):
        market_row = market_categories.get(category, {})
        store_row = store.get(category, {})
        days_of_cover = cover.get(category)
        categories.append(
            {
                "category": category,
                "market_growth": market_row.get("market_growth"),
                "store_units_sold": store_row.get("store_units_sold", 0.0),
                "store_revenue": store_row.get("store_revenue", 0.0),
                "store_daily_units": store_row.get("store_daily_units", 0.0),
                "days_of_cover": round(days_of_cover, 1) if days_of_cover is not None else None,
                "signal": _signal(market_growth=market_row.get("market_growth"), days_of_cover=days_of_cover),
            }
        )

    return {
        "status": "available",
        "state": provider.state,
        "source": provider.source_name,
        "as_of": statewide.get("as_of") or price.get("as_of"),
        "source_updated_at": statewide.get("source_updated_at") or price.get("source_updated_at"),
        "lookback_days": lookback_days,
        "statewide_growth": statewide.get("market_growth"),
        "average_retail_price_per_gram": price.get("current_per_gram"),
        "average_retail_price_change": price.get("change"),
        "categories": categories,
    }
