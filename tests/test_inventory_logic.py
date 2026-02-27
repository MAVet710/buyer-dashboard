"""
Unit tests for the Inventory Dashboard Buyer View logic.

Run with:  python -m pytest tests/test_inventory_logic.py -v
"""

import numpy as np
import pandas as pd
import pytest
import re
from datetime import datetime, timedelta

# ── Constants (mirrored from app.py) ─────────────────────────────────────────
UNKNOWN_DAYS_OF_SUPPLY = 999
INVENTORY_REORDER_DOH_THRESHOLD = 21
INVENTORY_OVERSTOCK_DOH_THRESHOLD = 90
INVENTORY_EXPIRING_SOON_DAYS = 60


# ── Pure helpers (mirrored from app.py buyer view section) ───────────────────

def _inv_status_badge(row) -> str:
    """
    Inventory status badge: Reorder / Healthy / Overstock / Expiring / No Stock.

    Args:
        row: pandas Series with at minimum 'onhandunits' and 'days_of_supply'.
             Optionally 'days_to_expire'.
    """
    on_hand = row["onhandunits"]
    doh = row["days_of_supply"]
    if on_hand <= 0:
        return "⬛ No Stock"
    if "days_to_expire" in row.index:
        days_exp = row["days_to_expire"]
        if pd.notna(days_exp) and days_exp < INVENTORY_EXPIRING_SOON_DAYS:
            return "⚠️ Expiring"
    if 0 < doh <= INVENTORY_REORDER_DOH_THRESHOLD:
        return "🔴 Reorder"
    if doh >= INVENTORY_OVERSTOCK_DOH_THRESHOLD:
        return "🟠 Overstock"
    return "✅ Healthy"


def _compute_doh(on_hand: float, daily_run_rate: float) -> float:
    """Compute days-of-hand given on-hand units and daily run rate."""
    if daily_run_rate <= 0:
        return UNKNOWN_DAYS_OF_SUPPLY
    return on_hand / daily_run_rate


def _compute_avg_weekly_sales(total_sold: float, window_days: int) -> float:
    """Avg weekly sales = total sold / (window_days / 7)."""
    if window_days <= 0:
        return 0.0
    return (total_sold / window_days) * 7


def _filter_by_expiration_window(df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Filter dataframe rows by expiration window label (<30 days, <60 days, <90 days)."""
    exp_days_map = {"<30 days": 30, "<60 days": 60, "<90 days": 90}
    if window == "Any" or "days_to_expire" not in df.columns:
        return df
    limit = exp_days_map[window]
    return df[df["days_to_expire"].notna() & (df["days_to_expire"] < limit)]


def _make_sku_row(
    itemname="SKU-A",
    on_hand=100.0,
    daily_run_rate=1.0,
    days_to_expire=None,
) -> pd.Series:
    """Helper to build a minimal SKU row Series for badge testing."""
    doh = _compute_doh(on_hand, daily_run_rate)
    data = {
        "itemname": itemname,
        "onhandunits": on_hand,
        "days_of_supply": doh,
        "avg_weekly_sales": daily_run_rate * 7,
    }
    if days_to_expire is not None:
        data["days_to_expire"] = days_to_expire
    return pd.Series(data)


# ── Tests: Status Badge ───────────────────────────────────────────────────────

class TestInvStatusBadge:
    def test_no_stock(self):
        row = _make_sku_row(on_hand=0.0, daily_run_rate=1.0)
        assert _inv_status_badge(row) == "⬛ No Stock"

    def test_reorder_at_threshold(self):
        # DOH == INVENTORY_REORDER_DOH_THRESHOLD → Reorder
        row = _make_sku_row(on_hand=float(INVENTORY_REORDER_DOH_THRESHOLD), daily_run_rate=1.0)
        assert _inv_status_badge(row) == "🔴 Reorder"

    def test_reorder_below_threshold(self):
        row = _make_sku_row(on_hand=10.0, daily_run_rate=1.0)  # DOH = 10
        assert _inv_status_badge(row) == "🔴 Reorder"

    def test_healthy(self):
        # DOH between REORDER and OVERSTOCK thresholds → Healthy
        row = _make_sku_row(on_hand=50.0, daily_run_rate=1.0)  # DOH = 50
        assert _inv_status_badge(row) == "✅ Healthy"

    def test_overstock_at_threshold(self):
        # DOH == INVENTORY_OVERSTOCK_DOH_THRESHOLD → Overstock
        row = _make_sku_row(on_hand=float(INVENTORY_OVERSTOCK_DOH_THRESHOLD), daily_run_rate=1.0)
        assert _inv_status_badge(row) == "🟠 Overstock"

    def test_overstock_above_threshold(self):
        row = _make_sku_row(on_hand=200.0, daily_run_rate=1.0)  # DOH = 200
        assert _inv_status_badge(row) == "🟠 Overstock"

    def test_no_velocity_gives_overstock(self):
        # daily_run_rate=0 → DOH = UNKNOWN (999) ≥ OVERSTOCK threshold → Overstock
        row = _make_sku_row(on_hand=50.0, daily_run_rate=0.0)
        assert _inv_status_badge(row) == "🟠 Overstock"

    def test_expiring_overrides_healthy(self):
        # DOH is healthy but expiry is soon → Expiring
        row = _make_sku_row(on_hand=50.0, daily_run_rate=1.0, days_to_expire=30)
        assert _inv_status_badge(row) == "⚠️ Expiring"

    def test_expiring_overrides_overstock(self):
        # Even overstock SKUs get Expiring badge when expiry is soon
        row = _make_sku_row(on_hand=500.0, daily_run_rate=1.0, days_to_expire=10)
        assert _inv_status_badge(row) == "⚠️ Expiring"

    def test_expiring_at_boundary(self):
        # days_to_expire == INVENTORY_EXPIRING_SOON_DAYS → NOT expiring (strict <)
        row = _make_sku_row(on_hand=50.0, daily_run_rate=1.0,
                            days_to_expire=INVENTORY_EXPIRING_SOON_DAYS)
        # 60 days is NOT < 60, so should be Healthy
        assert _inv_status_badge(row) == "✅ Healthy"

    def test_expiring_just_below_boundary(self):
        row = _make_sku_row(on_hand=50.0, daily_run_rate=1.0,
                            days_to_expire=INVENTORY_EXPIRING_SOON_DAYS - 1)
        assert _inv_status_badge(row) == "⚠️ Expiring"

    def test_no_expiry_column_does_not_raise(self):
        # Row without days_to_expire → should not raise
        row = _make_sku_row(on_hand=50.0, daily_run_rate=1.0)
        result = _inv_status_badge(row)
        assert result in {"✅ Healthy", "🔴 Reorder", "🟠 Overstock"}


# ── Tests: DOH Computation ────────────────────────────────────────────────────

class TestDOHForBuyer:
    def test_basic_doh(self):
        assert _compute_doh(70.0, 1.0) == pytest.approx(70.0)

    def test_zero_rate_gives_unknown(self):
        assert _compute_doh(100.0, 0.0) == UNKNOWN_DAYS_OF_SUPPLY

    def test_zero_on_hand_gives_zero_doh(self):
        assert _compute_doh(0.0, 5.0) == pytest.approx(0.0)

    def test_reorder_classification(self):
        doh = _compute_doh(15.0, 1.0)  # 15 days
        assert doh <= INVENTORY_REORDER_DOH_THRESHOLD

    def test_overstock_classification(self):
        doh = _compute_doh(100.0, 1.0)  # 100 days
        assert doh >= INVENTORY_OVERSTOCK_DOH_THRESHOLD


# ── Tests: Avg Weekly Sales ───────────────────────────────────────────────────

class TestAvgWeeklySales:
    def test_28_day_window(self):
        # 28 sold in 28 days = 7/week
        assert _compute_avg_weekly_sales(28.0, 28) == pytest.approx(7.0)

    def test_56_day_window(self):
        # 56 sold in 56 days = 7/week
        assert _compute_avg_weekly_sales(56.0, 56) == pytest.approx(7.0)

    def test_zero_window_returns_zero(self):
        assert _compute_avg_weekly_sales(100.0, 0) == 0.0

    def test_velocity_window_impact(self):
        # Same sales, shorter window → higher weekly rate
        rate_28 = _compute_avg_weekly_sales(56.0, 28)
        rate_56 = _compute_avg_weekly_sales(56.0, 56)
        assert rate_28 == pytest.approx(rate_56 * 2)


# ── Tests: Expiration Window Filter ──────────────────────────────────────────

class TestExpirationWindowFilter:
    def _make_df(self):
        return pd.DataFrame({
            "itemname": ["A", "B", "C", "D"],
            "onhandunits": [10, 20, 30, 40],
            "days_to_expire": [20.0, 45.0, 75.0, None],
        })

    def test_any_returns_all(self):
        df = self._make_df()
        result = _filter_by_expiration_window(df, "Any")
        assert len(result) == 4

    def test_less_than_30(self):
        df = self._make_df()
        result = _filter_by_expiration_window(df, "<30 days")
        assert len(result) == 1
        assert result["itemname"].values[0] == "A"

    def test_less_than_60(self):
        df = self._make_df()
        result = _filter_by_expiration_window(df, "<60 days")
        assert len(result) == 2
        assert set(result["itemname"].tolist()) == {"A", "B"}

    def test_less_than_90(self):
        df = self._make_df()
        result = _filter_by_expiration_window(df, "<90 days")
        assert len(result) == 3
        assert set(result["itemname"].tolist()) == {"A", "B", "C"}

    def test_null_expiry_excluded(self):
        df = self._make_df()
        result = _filter_by_expiration_window(df, "<30 days")
        # Row D has None days_to_expire and should not appear
        assert "D" not in result["itemname"].tolist()

    def test_no_expiry_column_returns_all(self):
        df = pd.DataFrame({"itemname": ["X", "Y"], "onhandunits": [10, 20]})
        result = _filter_by_expiration_window(df, "<60 days")
        assert len(result) == 2  # column missing → return all


# ── Tests: KPI Strip Values ───────────────────────────────────────────────────

class TestInventoryKPIs:
    def _make_merged_df(self):
        return pd.DataFrame({
            "itemname": ["A", "B", "C", "D", "E"],
            "onhandunits": [50.0, 100.0, 0.0, 200.0, 30.0],
            "days_of_supply": [10.0, 50.0, 0.0, 120.0, 999.0],
            "avg_weekly_sales": [35.0, 14.0, 0.0, 8.0, 0.0],
            "unit_cost": [5.0, 10.0, 8.0, 2.0, 15.0],
            "days_to_expire": [20.0, None, None, None, 30.0],
            "status": [
                "🔴 Reorder", "✅ Healthy", "⬛ No Stock", "🟠 Overstock", "⚠️ Expiring"
            ],
        })

    def test_skus_in_stock_count(self):
        df = self._make_merged_df()
        assert int((df["onhandunits"] > 0).sum()) == 4

    def test_total_dollars_on_hand(self):
        df = self._make_merged_df()
        df["dollars_on_hand"] = df["onhandunits"] * df["unit_cost"]
        expected = 50 * 5 + 100 * 10 + 0 * 8 + 200 * 2 + 30 * 15
        assert df["dollars_on_hand"].sum() == pytest.approx(expected)

    def test_reorder_count(self):
        df = self._make_merged_df()
        assert int((df["status"] == "🔴 Reorder").sum()) == 1

    def test_overstock_count(self):
        df = self._make_merged_df()
        assert int((df["status"] == "🟠 Overstock").sum()) == 1

    def test_expiring_count(self):
        df = self._make_merged_df()
        assert int((df["status"] == "⚠️ Expiring").sum()) == 1

    def test_earliest_expiry_per_sku(self):
        """Earliest expiration per SKU must use min aggregation."""
        inv = pd.DataFrame({
            "itemname": ["Product A", "Product A", "Product B"],
            "onhandunits": [10.0, 20.0, 5.0],
            "expiration_date": pd.to_datetime(["2026-03-01", "2026-06-01", "2026-04-01"]),
        })
        agg = inv.groupby("itemname").agg(
            onhandunits=("onhandunits", "sum"),
            expiration_date=("expiration_date", "min"),
        ).reset_index()
        prod_a = agg[agg["itemname"] == "Product A"]["expiration_date"].values[0]
        assert pd.Timestamp(prod_a) == pd.Timestamp("2026-03-01")
        assert agg[agg["itemname"] == "Product A"]["onhandunits"].values[0] == 30.0


# ── Vault-only Room filtering (mirrored from filter_vault_inventory in app.py) ─

def _filter_vault_inventory(df):
    """Mirror of app.py filter_vault_inventory for unit testing."""
    norm_cols = {str(c).strip().lower(): c for c in df.columns}
    room_col = norm_cols.get("room")

    if room_col is None:
        raise ValueError(
            "The inventory file is missing a 'Room' column. "
            "Please upload the correct inventory report that includes a 'Room' column "
            "(expected values: Vault, Quarantine, Employee Stock, …). "
            "Only Vault rows are used by this dashboard."
        )

    room_norm = df[room_col].apply(lambda v: str(v).strip().lower())
    mask = room_norm == "vault"
    n_included = int(mask.sum())
    n_excluded = int((~mask).sum())
    return df[mask].copy(), n_included, n_excluded


class TestFilterVaultInventory:
    def _make_df(self, rooms):
        return pd.DataFrame({
            "Product": [f"SKU-{i}" for i in range(len(rooms))],
            "Available": [10] * len(rooms),
            "Room": rooms,
        })

    def test_vault_case_insensitive_lower(self):
        df = self._make_df(["vault", "Quarantine"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 1
        assert excluded == 1
        assert list(result["Product"]) == ["SKU-0"]

    def test_vault_case_insensitive_upper(self):
        df = self._make_df(["VAULT", "employee stock"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 1
        assert excluded == 1
        assert list(result["Product"]) == ["SKU-0"]

    def test_vault_mixed_case(self):
        df = self._make_df(["Vault", "Quarantine", "Employee Stock"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 1
        assert excluded == 2

    def test_non_vault_all_excluded(self):
        df = self._make_df(["Quarantine", "Employee Stock"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 0
        assert excluded == 2
        assert len(result) == 0

    def test_all_vault_included(self):
        df = self._make_df(["Vault", "vault", "VAULT"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 3
        assert excluded == 0
        assert len(result) == 3

    def test_missing_room_column_raises(self):
        df = pd.DataFrame({"Product": ["SKU-A"], "Available": [5]})
        with pytest.raises(ValueError, match="missing a 'Room' column"):
            _filter_vault_inventory(df)

    def test_room_column_with_whitespace(self):
        df = self._make_df([" Vault ", "Quarantine"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 1
        assert list(result["Product"]) == ["SKU-0"]

    def test_counts_correct_for_mixed_rooms(self):
        df = self._make_df(["Vault", "vault", "Quarantine", "Employee Stock", "VAULT"])
        result, included, excluded = _filter_vault_inventory(df)
        assert included == 3
        assert excluded == 2


# ── Helpers mirrored from app.py for alias detection ─────────────────────────

INV_COST_ALIASES = [
    "cost", "unitcost", "unit cost", "cogs", "costprice", "cost price",
    "wholesale", "wholesaleprice", "wholesale price",
    "currentprice", "current price",
]


def _normalize_col(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _detect_column(columns, aliases):
    norm_map = {_normalize_col(c): c for c in columns}
    for alias in aliases:
        if alias in norm_map:
            return norm_map[alias]
    return None


# ── Tests: Cost Column Alias Detection ───────────────────────────────────────

class TestCostColumnAliasDetection:
    def _detect(self, header):
        return _detect_column([header], [_normalize_col(a) for a in INV_COST_ALIASES])

    def test_current_price_exact(self):
        assert self._detect("Current price") == "Current price"

    def test_current_price_all_caps(self):
        assert self._detect("CURRENT PRICE") == "CURRENT PRICE"

    def test_current_price_no_space(self):
        assert self._detect("currentprice") == "currentprice"

    def test_unit_cost_still_detected(self):
        assert self._detect("unit cost") == "unit cost"

    def test_unit_cost_camel(self):
        assert self._detect("UnitCost") == "UnitCost"

    def test_cost_detected(self):
        assert self._detect("Cost") == "Cost"

    def test_wholesale_detected(self):
        assert self._detect("Wholesale") == "Wholesale"

    def test_unknown_column_returns_none(self):
        assert self._detect("retail price") is None


# ── Tests: PO Builder price carry-over (unit_cost / 2) ───────────────────────

class TestPOBuilderPriceCarryOver:
    """Validate that unit_cost / 2 logic matches the PO Builder implementation."""

    def _compute_price(self, unit_cost_value):
        """Mirror of the price computation in the 'Add All Reorder ASAP Lines to PO' handler."""
        try:
            _raw_cost = pd.to_numeric(unit_cost_value, errors="coerce")
            return float(_raw_cost) / 2 if pd.notna(_raw_cost) else 0.0
        except (ValueError, TypeError):
            return 0.0

    def test_price_is_half_of_unit_cost(self):
        assert self._compute_price(20.0) == 10.0

    def test_price_zero_when_unit_cost_missing(self):
        assert self._compute_price(None) == 0.0

    def test_price_zero_when_unit_cost_nan(self):
        assert self._compute_price(float("nan")) == 0.0

    def test_price_zero_when_unit_cost_zero(self):
        assert self._compute_price(0.0) == 0.0

    def test_price_handles_string_number(self):
        assert self._compute_price("14.50") == 7.25

    def test_price_zero_on_invalid_string(self):
        assert self._compute_price("n/a") == 0.0

    def test_current_price_column_in_display(self):
        """Verify that the 'Current Price' display column equals unit_cost / 2."""
        reorder_rows = pd.DataFrame({
            "subcategory": ["Flower"],
            "packagesize": ["3.5g"],
            "unit_cost": [30.0],
        })
        reorder_rows["Current Price"] = (
            pd.to_numeric(reorder_rows["unit_cost"], errors="coerce").fillna(0) / 2
        ).round(2)
        assert reorder_rows["Current Price"].iloc[0] == 15.0


# ── Tests: unit_cost aggregation (median) into inv_summary / detail ───────────

class TestInventoryUnitCostAggregation:
    """Validate that unit_cost is aggregated via median from item-level into
    the category/strain/packagesize summary that feeds detail_cached_df."""

    def _make_inv_df(self):
        """Multiple batches of the same product at different costs."""
        return pd.DataFrame({
            "subcategory": ["Flower", "Flower", "Flower", "Edibles"],
            "strain_type": ["sativa", "sativa", "indica", "none"],
            "packagesize": ["3.5g", "3.5g", "3.5g", "10mg"],
            "onhandunits": [10.0, 20.0, 5.0, 50.0],
            "unit_cost": [20.0, 30.0, 40.0, 5.0],
        })

    def _aggregate(self, inv_df):
        """Mirror of app.py inv_summary + cost merge logic."""
        inv_summary = (
            inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"]
            .sum()
            .reset_index()
        )
        _cost_summary = (
            inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["unit_cost"]
            .median()
            .reset_index()
        )
        return inv_summary.merge(_cost_summary, on=["subcategory", "strain_type", "packagesize"], how="left")

    def test_median_cost_for_multi_batch_product(self):
        """Flower/sativa/3.5g has two batches with costs [20.0, 30.0] → median = 25.0.
        (Flower/indica/3.5g is a separate strain group and is not included.)"""
        result = self._aggregate(self._make_inv_df())
        row = result[
            (result["subcategory"] == "Flower") &
            (result["strain_type"] == "sativa") &
            (result["packagesize"] == "3.5g")
        ]
        assert row["unit_cost"].iloc[0] == pytest.approx(25.0)

    def test_single_batch_cost_preserved(self):
        """Flower/indica/3.5g has a single cost of 40.0 → median = 40.0."""
        result = self._aggregate(self._make_inv_df())
        row = result[
            (result["subcategory"] == "Flower") &
            (result["strain_type"] == "indica") &
            (result["packagesize"] == "3.5g")
        ]
        assert row["unit_cost"].iloc[0] == pytest.approx(40.0)

    def test_unit_cost_present_in_summary(self):
        """unit_cost column must exist in the aggregated summary."""
        result = self._aggregate(self._make_inv_df())
        assert "unit_cost" in result.columns

    def test_summary_without_cost_column(self):
        """If inv_df has no unit_cost column, no cost is merged into inv_summary."""
        inv_df = self._make_inv_df().drop(columns=["unit_cost"])
        inv_summary = (
            inv_df.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["onhandunits"]
            .sum()
            .reset_index()
        )
        # No cost merge happens — unit_cost should not appear
        assert "unit_cost" not in inv_summary.columns

    def test_po_price_from_aggregated_cost(self):
        """PO price for a row should be median(unit_cost) / 2."""
        result = self._aggregate(self._make_inv_df())
        row = result[
            (result["subcategory"] == "Flower") &
            (result["strain_type"] == "sativa") &
            (result["packagesize"] == "3.5g")
        ]
        unit_cost = row["unit_cost"].iloc[0]
        assert round(unit_cost / 2, 2) == 12.5
