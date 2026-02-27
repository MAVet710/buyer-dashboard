"""
Lightweight validation tests for Slow Movers & Trends logic.

Run with:  python -m pytest tests/test_slow_movers_logic.py -v
"""

import numpy as np
import pandas as pd
import pytest

# ── Constants (mirrored from app.py) ──────────────────────────────────────────
UNKNOWN_DAYS_OF_SUPPLY = 999
SLOW_MOVER_DEFAULT_DOH_THRESHOLD = 60


# ── Pure-function helpers (duplicated here to keep tests self-contained) ──────

def _sm_action_badge(days_of_supply: float, weekly_sales: float, on_hand: float) -> str:
    if on_hand <= 0:
        return "⬛ No Stock"
    if weekly_sales <= 0 or days_of_supply >= UNKNOWN_DAYS_OF_SUPPLY:
        return "🔴 Investigate"
    if days_of_supply > 180:
        return "🔴 Promo / Stop Reorder"
    if days_of_supply > 120:
        return "🟠 Markdown"
    if days_of_supply > 90:
        return "🟡 Watch"
    if days_of_supply > 60:
        return "🟢 Monitor"
    return "✅ Healthy"


def _sm_score(days_of_supply: float, weekly_sales: float) -> float:
    if weekly_sales <= 0:
        return 100.0
    return round(min(days_of_supply / 180.0, 1.0) * 100.0, 1)


def _suggest_discount(days: float) -> str:
    if days > 180:
        return "30-50% (Urgent)"
    elif days > 120:
        return "20-30% (High Priority)"
    elif days > 90:
        return "15-20% (Medium Priority)"
    elif days > 60:
        return "10-15% (Low Priority)"
    else:
        return "No discount needed"


def _compute_velocity(sales_df: pd.DataFrame, name_col: str, qty_col: str,
                      window_days: int) -> pd.DataFrame:
    """Re-implementation of the velocity window logic used in the Slow Movers page."""
    df = sales_df.groupby(name_col)[qty_col].sum().reset_index()
    df = df.rename(columns={name_col: "product", qty_col: "total_sold"})
    df["daily_run_rate"] = df["total_sold"] / max(window_days, 1)
    df["avg_weekly_sales"] = df["daily_run_rate"] * 7
    return df


def _compute_doh(inv_df: pd.DataFrame, sales_vel: pd.DataFrame) -> pd.DataFrame:
    """Merge inventory with velocity to produce days_of_supply."""
    merged = inv_df.merge(sales_vel, left_on="itemname", right_on="product", how="left")
    merged["daily_run_rate"] = merged["daily_run_rate"].fillna(0)
    merged["days_of_supply"] = np.where(
        merged["daily_run_rate"] > 0,
        merged["onhandunits"] / merged["daily_run_rate"],
        UNKNOWN_DAYS_OF_SUPPLY,
    )
    return merged


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestActionBadge:
    def test_no_stock(self):
        assert _sm_action_badge(200, 5.0, 0) == "⬛ No Stock"

    def test_no_velocity_investigate(self):
        assert _sm_action_badge(50, 0, 10) == "🔴 Investigate"

    def test_unknown_doh_investigate(self):
        assert _sm_action_badge(UNKNOWN_DAYS_OF_SUPPLY, 1.0, 10) == "🔴 Investigate"

    def test_promo_stop_reorder(self):
        assert _sm_action_badge(200, 2.0, 50) == "🔴 Promo / Stop Reorder"

    def test_markdown(self):
        assert _sm_action_badge(150, 2.0, 50) == "🟠 Markdown"

    def test_watch(self):
        assert _sm_action_badge(100, 2.0, 50) == "🟡 Watch"

    def test_monitor(self):
        assert _sm_action_badge(70, 2.0, 50) == "🟢 Monitor"

    def test_healthy(self):
        assert _sm_action_badge(30, 5.0, 100) == "✅ Healthy"


class TestSlowMoverScore:
    def test_zero_velocity_returns_100(self):
        assert _sm_score(999, 0) == 100.0

    def test_180_days_returns_100(self):
        assert _sm_score(180, 1.0) == 100.0

    def test_90_days_returns_50(self):
        assert _sm_score(90, 1.0) == 50.0

    def test_above_ceiling_capped(self):
        assert _sm_score(360, 1.0) == 100.0

    def test_0_days_returns_0(self):
        assert _sm_score(0, 1.0) == 0.0


class TestSuggestDiscount:
    def test_urgent(self):
        assert "Urgent" in _suggest_discount(200)

    def test_high_priority(self):
        assert "High Priority" in _suggest_discount(130)

    def test_medium_priority(self):
        assert "Medium Priority" in _suggest_discount(95)

    def test_low_priority(self):
        assert "Low Priority" in _suggest_discount(65)

    def test_no_discount(self):
        assert "No discount" in _suggest_discount(30)


class TestVelocityWindow:
    """Ensure velocity changes correctly when the window changes."""

    def _make_sales(self):
        return pd.DataFrame({
            "product": ["A", "A", "B"],
            "qty": [28, 28, 14],
        })

    def test_28day_window_doubles_rate_vs_56(self):
        sales = self._make_sales()
        v28 = _compute_velocity(sales, "product", "qty", 28)
        v56 = _compute_velocity(sales, "product", "qty", 56)
        rate_a_28 = v28[v28["product"] == "A"]["daily_run_rate"].values[0]
        rate_a_56 = v56[v56["product"] == "A"]["daily_run_rate"].values[0]
        assert pytest.approx(rate_a_28, rel=1e-6) == rate_a_56 * 2

    def test_avg_weekly_sales_is_7x_daily(self):
        sales = self._make_sales()
        vel = _compute_velocity(sales, "product", "qty", 28)
        row_a = vel[vel["product"] == "A"].iloc[0]
        assert pytest.approx(row_a["avg_weekly_sales"]) == row_a["daily_run_rate"] * 7


class TestDOHComputation:
    def test_doh_correct(self):
        inv = pd.DataFrame({"itemname": ["A"], "onhandunits": [70.0]})
        vel = pd.DataFrame({
            "product": ["A"],
            "total_sold": [70],
            "daily_run_rate": [1.0],
            "avg_weekly_sales": [7.0],
        })
        merged = _compute_doh(inv, vel)
        assert merged["days_of_supply"].values[0] == pytest.approx(70.0)

    def test_no_sales_gives_unknown_doh(self):
        inv = pd.DataFrame({"itemname": ["X"], "onhandunits": [50.0]})
        vel = pd.DataFrame({
            "product": ["Y"],
            "total_sold": [0],
            "daily_run_rate": [0.0],
            "avg_weekly_sales": [0.0],
        })
        merged = _compute_doh(inv, vel)
        assert merged["days_of_supply"].values[0] == UNKNOWN_DAYS_OF_SUPPLY

    def test_slow_mover_threshold_filter(self):
        inv = pd.DataFrame({
            "itemname": ["Fast", "Slow"],
            "onhandunits": [10.0, 200.0],
        })
        vel = pd.DataFrame({
            "product": ["Fast", "Slow"],
            "total_sold": [100, 10],
            "daily_run_rate": [10.0, 0.1],
            "avg_weekly_sales": [70.0, 0.7],
        })
        merged = _compute_doh(inv, vel)
        slow = merged[merged["days_of_supply"] > SLOW_MOVER_DEFAULT_DOH_THRESHOLD]
        assert len(slow) == 1
        assert slow["itemname"].values[0] == "Slow"


class TestKPISummary:
    """Validate KPI tile calculations."""

    def _make_working_df(self):
        return pd.DataFrame({
            "itemname": ["A", "B", "C"],
            "onhandunits": [100.0, 200.0, 50.0],
            "days_of_supply": [70.0, 150.0, 30.0],
            "category": ["Flower", "Vape", "Flower"],
        })

    def test_slow_count(self):
        df = self._make_working_df()
        slow_count = len(df[df["days_of_supply"] > SLOW_MOVER_DEFAULT_DOH_THRESHOLD])
        assert slow_count == 2

    def test_median_doh(self):
        df = self._make_working_df()
        df_no_unknown = df["days_of_supply"].replace(UNKNOWN_DAYS_OF_SUPPLY, np.nan)
        assert df_no_unknown.median() == pytest.approx(70.0)

    def test_worst_category_by_units(self):
        df = self._make_working_df()
        worst = df.groupby("category")["onhandunits"].sum().idxmax()
        # Vape has 200 units, Flower has 150 units total
        assert worst == "Vape"
