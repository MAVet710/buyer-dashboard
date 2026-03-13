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

INV_NAME_ALIASES = [
    "product", "productname", "item", "itemname", "name", "skuname",
    "skuid", "product name", "product_name", "product title", "title",
]
INV_CAT_ALIASES = [
    "category", "subcategory", "productcategory", "department",
    "mastercategory", "product category", "cannabis", "product_category",
    "ecomm category", "ecommcategory",
]
INV_QTY_ALIASES = [
    "available", "onhand", "onhandunits", "quantity", "qty",
    "quantityonhand", "instock", "currentquantity", "current quantity",
    "inventoryavailable", "inventory available", "available quantity",
    "med total", "medtotal",
    "med sellable", "medsellable",
]
INV_COST_ALIASES = [
    "cost", "unitcost", "unit cost", "cogs", "costprice", "cost price",
    "wholesale", "wholesaleprice", "wholesale price",
    "currentprice", "current price",
]
INV_RETAIL_PRICE_ALIASES = [
    "medprice", "med price", "retail", "retailprice", "retail price", "msrp",
]


def _normalize_col(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _detect_column(columns, aliases):
    norm_map = {_normalize_col(c): c for c in columns}
    for alias in aliases:
        if alias in norm_map:
            return norm_map[alias]
    return None


def _parse_currency_to_float(series):
    """Mirror of app.py parse_currency_to_float."""
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"^\$", "", regex=True)
        .str.replace(",", "", regex=False)
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
    )


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

    def test_retail_price_not_in_cost_aliases(self):
        assert self._detect("retail price") is None


# ── Tests: Retail Price Alias Detection ──────────────────────────────────────

class TestRetailPriceAliasDetection:
    """Verify that retail price column headers are correctly detected."""

    def _detect(self, header):
        return _detect_column([header], [_normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])

    def test_med_price_exact(self):
        assert self._detect("Med Price") == "Med Price"

    def test_med_price_all_caps(self):
        assert self._detect("MED PRICE") == "MED PRICE"

    def test_med_price_no_space(self):
        assert self._detect("medprice") == "medprice"

    def test_retail_exact(self):
        assert self._detect("retail") == "retail"

    def test_retail_price_detected(self):
        assert self._detect("Retail Price") == "Retail Price"

    def test_msrp_detected(self):
        assert self._detect("MSRP") == "MSRP"

    def test_wholesale_cost_not_detected_as_retail(self):
        assert self._detect("Wholesale") is None

    def test_unit_cost_not_detected_as_retail(self):
        assert self._detect("unit cost") is None


# ── Tests: Dutchie Export Auto-Detection ─────────────────────────────────────

class TestDutchieExportAutoDetection:
    """Verify that Dutchie inventory export headers auto-detect correctly."""

    def _detect_name(self, header):
        return _detect_column([header], [_normalize_col(a) for a in INV_NAME_ALIASES])

    def _detect_cat(self, header):
        return _detect_column([header], [_normalize_col(a) for a in INV_CAT_ALIASES])

    def _detect_qty(self, header):
        return _detect_column([header], [_normalize_col(a) for a in INV_QTY_ALIASES])

    def test_name_column_detected(self):
        assert self._detect_name("Name") == "Name"

    def test_ecomm_category_spaced_detected(self):
        assert self._detect_cat("EComm Category") == "EComm Category"

    def test_ecomm_category_lowercase_detected(self):
        assert self._detect_cat("ecomm category") == "ecomm category"

    def test_med_total_detected(self):
        assert self._detect_qty("Med Total") == "Med Total"

    def test_med_total_lowercase_detected(self):
        assert self._detect_qty("med total") == "med total"

    def test_med_sellable_detected(self):
        assert self._detect_qty("Med Sellable") == "Med Sellable"

    def test_med_sellable_lowercase_detected(self):
        assert self._detect_qty("med sellable") == "med sellable"

    def test_full_dutchie_row_resolves(self):
        """End-to-end: headers from a real Dutchie export should all resolve."""
        raw_headers = ["Name", "EComm Category", "Med Total"]
        # Simulate app.py normalisation: lower + strip
        columns = [h.strip().lower() for h in raw_headers]

        name_col = _detect_column(columns, [_normalize_col(a) for a in INV_NAME_ALIASES])
        cat_col = _detect_column(columns, [_normalize_col(a) for a in INV_CAT_ALIASES])
        qty_col = _detect_column(columns, [_normalize_col(a) for a in INV_QTY_ALIASES])

        assert name_col == "name"
        assert cat_col == "ecomm category"
        assert qty_col == "med total"


# ── Tests: Currency Parsing ───────────────────────────────────────────────────

class TestParseCurrencyToFloat:
    """Verify parse_currency_to_float handles all common formats."""

    def _parse(self, values):
        return _parse_currency_to_float(pd.Series(values))

    def test_plain_float_string(self):
        result = self._parse(["45.00"])
        assert result.iloc[0] == pytest.approx(45.0)

    def test_dollar_sign_stripped(self):
        result = self._parse(["$45.00"])
        assert result.iloc[0] == pytest.approx(45.0)

    def test_dollar_with_comma(self):
        result = self._parse(["$1,234.56"])
        assert result.iloc[0] == pytest.approx(1234.56)

    def test_blank_becomes_nan(self):
        result = self._parse([""])
        assert pd.isna(result.iloc[0])

    def test_none_becomes_nan(self):
        result = self._parse([None])
        assert pd.isna(result.iloc[0])

    def test_invalid_string_becomes_nan(self):
        result = self._parse(["n/a"])
        assert pd.isna(result.iloc[0])

    def test_mixed_series(self):
        result = self._parse(["$10.00", "", "$1,000.00", "n/a", "25.5"])
        assert result.iloc[0] == pytest.approx(10.0)
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == pytest.approx(1000.0)
        assert pd.isna(result.iloc[3])
        assert result.iloc[4] == pytest.approx(25.5)


# ── Tests: retail_dollars_on_hand Computation ────────────────────────────────

class TestRetailDollarsOnHand:
    """Verify retail_dollars_on_hand = onhandunits * retail_price."""

    def _build_merged(self, rows):
        """Build a minimal _b_merged-style dataframe and compute retail_dollars_on_hand."""
        df = pd.DataFrame(rows)
        df["retail_price"] = _parse_currency_to_float(df["retail_price"])
        df["retail_dollars_on_hand"] = df["onhandunits"] * df["retail_price"]
        return df

    def test_basic_computation(self):
        df = self._build_merged([
            {"itemname": "OG Kush 3.5g", "onhandunits": 10, "retail_price": "$45.00"},
        ])
        assert df["retail_dollars_on_hand"].iloc[0] == pytest.approx(450.0)

    def test_currency_string_parsed_correctly(self):
        df = self._build_merged([
            {"itemname": "Blue Dream 1g", "onhandunits": 5, "retail_price": "$12.50"},
        ])
        assert df["retail_dollars_on_hand"].iloc[0] == pytest.approx(62.5)

    def test_zero_units_gives_zero_value(self):
        df = self._build_merged([
            {"itemname": "Out of Stock SKU", "onhandunits": 0, "retail_price": "$30.00"},
        ])
        assert df["retail_dollars_on_hand"].iloc[0] == pytest.approx(0.0)

    def test_nan_retail_price_gives_nan_value(self):
        df = self._build_merged([
            {"itemname": "No Price SKU", "onhandunits": 5, "retail_price": ""},
        ])
        assert pd.isna(df["retail_dollars_on_hand"].iloc[0])

    def test_unit_cost_and_retail_price_are_independent(self):
        """Ensure cost-basis and retail-basis values differ when prices differ."""
        df = pd.DataFrame([{
            "itemname": "Test SKU",
            "onhandunits": 10,
            "unit_cost": 20.0,
            "retail_price": "$35.00",
        }])
        df["retail_price"] = _parse_currency_to_float(df["retail_price"])
        df["dollars_on_hand"] = df["onhandunits"] * df["unit_cost"]
        df["retail_dollars_on_hand"] = df["onhandunits"] * df["retail_price"]
        assert df["dollars_on_hand"].iloc[0] == pytest.approx(200.0)
        assert df["retail_dollars_on_hand"].iloc[0] == pytest.approx(350.0)


# ── Tests: Buyer View KPIs / columns with both unit_cost and retail_price ─────

class TestBuyerViewBothPrices:
    """Validate Buyer View KPI and column logic when both prices are present."""

    def _make_merged_df(self):
        """Minimal _b_merged-style dataframe with both unit_cost and retail_price."""
        df = pd.DataFrame({
            "itemname": ["SKU A", "SKU B", "SKU C"],
            "onhandunits": [10.0, 5.0, 0.0],
            "unit_cost": [20.0, 30.0, 15.0],
            "retail_price": [35.0, 50.0, 25.0],
            "days_of_supply": [30.0, 90.0, 999.0],
            "avg_weekly_sales": [2.0, 0.5, 0.0],
            "total_sold": [10.0, 5.0, 0.0],
            "daily_run_rate": [2 / 7, 0.5 / 7, 0.0],
            "status": ["✅ Healthy", "🟠 Overstock", "⬛ No Stock"],
        })
        df["dollars_on_hand"] = df["onhandunits"] * df["unit_cost"]
        df["retail_dollars_on_hand"] = df["onhandunits"] * df["retail_price"]
        return df

    def test_dollars_on_hand_cost_basis(self):
        df = self._make_merged_df()
        assert df["dollars_on_hand"].iloc[0] == pytest.approx(200.0)  # 10 * 20
        assert df["dollars_on_hand"].iloc[1] == pytest.approx(150.0)  # 5 * 30
        assert df["dollars_on_hand"].iloc[2] == pytest.approx(0.0)    # 0 * 15

    def test_retail_dollars_on_hand(self):
        df = self._make_merged_df()
        assert df["retail_dollars_on_hand"].iloc[0] == pytest.approx(350.0)  # 10 * 35
        assert df["retail_dollars_on_hand"].iloc[1] == pytest.approx(250.0)  # 5 * 50
        assert df["retail_dollars_on_hand"].iloc[2] == pytest.approx(0.0)    # 0 * 25

    def test_total_cost_kpi(self):
        df = self._make_merged_df()
        total_cost = df["dollars_on_hand"].sum()
        assert total_cost == pytest.approx(350.0)  # 200 + 150 + 0

    def test_total_retail_kpi(self):
        df = self._make_merged_df()
        total_retail = df["retail_dollars_on_hand"].sum()
        assert total_retail == pytest.approx(600.0)  # 350 + 250 + 0

    def test_both_columns_present_in_display_map(self):
        """Verify display column mapping includes both Unit Cost and Retail Price."""
        df = self._make_merged_df()
        dcmap = {}
        if "unit_cost" in df.columns:
            dcmap["Unit Cost"] = "unit_cost"
        if "retail_price" in df.columns:
            dcmap["Retail Price"] = "retail_price"
        if "dollars_on_hand" in df.columns:
            dcmap["$ On Hand (Cost)"] = "dollars_on_hand"
        if "retail_dollars_on_hand" in df.columns:
            dcmap["$ On Hand (Retail)"] = "retail_dollars_on_hand"
        assert "Unit Cost" in dcmap
        assert "Retail Price" in dcmap
        assert "$ On Hand (Cost)" in dcmap
        assert "$ On Hand (Retail)" in dcmap

    def test_cost_and_retail_kpis_shown_when_both_present(self):
        """Both dollars_on_hand and retail_dollars_on_hand exist → both KPIs shown."""
        df = self._make_merged_df()
        has_cost_kpi = "dollars_on_hand" in df.columns
        has_retail_kpi = "retail_dollars_on_hand" in df.columns
        assert has_cost_kpi
        assert has_retail_kpi

    def test_inventory_normalization_detects_med_price_as_retail(self):
        """Upload normalization: 'Med Price' column → retail_price after normalization."""
        raw = pd.DataFrame({
            "Name": ["OG Kush 3.5g", "Blue Dream 1g"],
            "EComm Sub Category": ["Flower", "Flower"],
            "Med Sellable": [10, 5],
            "Med Price": ["$45.00", "$12.50"],
        })
        raw.columns = raw.columns.astype(str).str.strip().str.lower()
        retail_col = _detect_column(raw.columns, [_normalize_col(a) for a in INV_RETAIL_PRICE_ALIASES])
        assert retail_col == "med price"
        raw = raw.rename(columns={retail_col: "retail_price"})
        raw["retail_price"] = _parse_currency_to_float(raw["retail_price"])
        assert raw["retail_price"].iloc[0] == pytest.approx(45.0)
        assert raw["retail_price"].iloc[1] == pytest.approx(12.5)


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
