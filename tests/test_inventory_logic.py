"""
Unit tests for the Inventory Dashboard Buyer View logic.

Run with:  python -m pytest tests/test_inventory_logic.py -v
"""

import numpy as np
import pandas as pd
import pytest
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
