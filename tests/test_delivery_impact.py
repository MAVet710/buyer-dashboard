"""
Unit tests for delivery_impact.py

Run with:  python -m pytest tests/test_delivery_impact.py -v
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from delivery_impact import (
    DELIVERY_WINDOW_DAYS,
    build_time_series,
    compute_delivery_kpis,
    find_sales_header_row,
    match_manifest_to_sales,
    normalize_product_name,
    parse_sales_report_bytes,
)


# ===========================================================================
# normalize_product_name
# ===========================================================================

class TestNormalizeProductName:
    def test_lowercases(self):
        assert normalize_product_name("Blue Dream") == "blue dream"

    def test_strips_gram_size(self):
        result = normalize_product_name("Blue Dream 3.5g")
        assert "3.5g" not in result
        assert "blue dream" in result

    def test_strips_mg_size(self):
        result = normalize_product_name("CBD Tincture 500mg")
        assert "500mg" not in result

    def test_strips_oz_size(self):
        result = normalize_product_name("Gummies 1oz")
        assert "1oz" not in result

    def test_removes_punctuation(self):
        result = normalize_product_name("Blue Dream - Premium!")
        assert "-" not in result
        assert "!" not in result

    def test_collapses_whitespace(self):
        result = normalize_product_name("  Blue   Dream  ")
        assert result == "blue dream"

    def test_numeric_tokens_kept(self):
        # Numbers not followed by a unit should remain
        result = normalize_product_name("Product #1")
        assert "1" in result

    def test_empty_string(self):
        assert normalize_product_name("") == ""


# ===========================================================================
# match_manifest_to_sales
# ===========================================================================

class TestMatchManifestToSales:
    def _sales(self):
        return [
            "Blue Dream 3.5g",
            "Sour Diesel",
            "OG Kush 1g",
            "CBD Tincture 500mg",
        ]

    def test_exact_match(self):
        matched, unmatched = match_manifest_to_sales(
            ["Sour Diesel"], self._sales()
        )
        assert "Sour Diesel" in matched
        assert matched["Sour Diesel"] == "Sour Diesel"
        assert unmatched == []

    def test_case_insensitive_exact_match(self):
        matched, unmatched = match_manifest_to_sales(
            ["sour diesel"], self._sales()
        )
        assert "sour diesel" in matched
        assert unmatched == []

    def test_normalised_match_strips_size(self):
        # Manifest says "Blue Dream" (no size), sales has "Blue Dream 3.5g"
        matched, unmatched = match_manifest_to_sales(
            ["Blue Dream"], self._sales()
        )
        assert "Blue Dream" in matched
        assert unmatched == []

    def test_fuzzy_match_close_name(self):
        matched, unmatched = match_manifest_to_sales(
            ["Sour Desiel"],  # typo
            ["Sour Diesel"],
            fuzzy_threshold=0.80,
        )
        assert "Sour Desiel" in matched
        assert unmatched == []

    def test_unmatched_returned(self):
        matched, unmatched = match_manifest_to_sales(
            ["Totally Unknown Product XYZ"],
            self._sales(),
        )
        assert "Totally Unknown Product XYZ" in unmatched
        assert len(matched) == 0

    def test_multiple_items_mixed(self):
        matched, unmatched = match_manifest_to_sales(
            ["Blue Dream", "Totally Unknown Product XYZ"],
            self._sales(),
        )
        assert "Blue Dream" in matched
        assert "Totally Unknown Product XYZ" in unmatched

    def test_empty_manifest(self):
        matched, unmatched = match_manifest_to_sales([], self._sales())
        assert matched == {}
        assert unmatched == []

    def test_empty_sales(self):
        matched, unmatched = match_manifest_to_sales(["Blue Dream"], [])
        assert "Blue Dream" in unmatched

    def test_high_threshold_prevents_fuzzy(self):
        # With threshold=1.0 only exact matches work
        matched, unmatched = match_manifest_to_sales(
            ["Sour Desiel"],
            ["Sour Diesel"],
            fuzzy_threshold=1.0,
        )
        assert "Sour Desiel" in unmatched


# ===========================================================================
# find_sales_header_row
# ===========================================================================

class TestFindSalesHeaderRow:
    def _csv(self, lines: list[str]) -> bytes:
        return "\n".join(lines).encode("utf-8")

    def test_no_preamble(self):
        csv = self._csv([
            "Order ID,Order Time,Product Name,Net Sales",
            "1001,2025-03-01 10:00,Blue Dream 3.5g,45.00",
        ])
        assert find_sales_header_row(csv) == 0

    def test_preamble_rows_skipped(self):
        csv = self._csv([
            "Export Date:,03/20/2026 11:17 AM",
            "Report Name:,Sales by Order",
            "Dispensary:,Acme Cannabis",
            "Order ID,Order Time,Product Name,Net Sales",
            "1001,2025-03-01 10:00,Blue Dream 3.5g,45.00",
        ])
        assert find_sales_header_row(csv) == 3

    def test_extra_columns_still_detected(self):
        csv = self._csv([
            "Meta:,value",
            "Order ID,Order Time,Customer Type,Product Name,Category,Total Inventory Sold,Net Sales",
        ])
        assert find_sales_header_row(csv) == 1

    def test_no_header_returns_zero(self):
        csv = self._csv([
            "Some random text",
            "More random text",
        ])
        assert find_sales_header_row(csv) == 0

    def test_case_insensitive_detection(self):
        csv = self._csv([
            "EXPORT DATE:,value",
            "order id,order time,product name,net sales",
        ])
        assert find_sales_header_row(csv) == 1


# ===========================================================================
# parse_sales_report_bytes
# ===========================================================================

class TestParseSalesReportBytes:
    def _make_csv(self, preamble_rows: int = 0) -> bytes:
        preamble = [
            f"Export Date:,03/20/2026",
            f"Report:,Sales",
        ][:preamble_rows]
        header = "Order ID,Order Time,Product Name,Category,Total Inventory Sold,Net Sales"
        data = [
            "1001,2025-03-01 10:00,Blue Dream 3.5g,Flower,2,90.00",
            "1002,2025-03-02 11:30,Sour Diesel,Flower,1,45.00",
            "1003,2025-03-03 14:00,CBD Tincture 500mg,Tinctures,1,35.00",
        ]
        lines = preamble + [header] + data
        return "\n".join(lines).encode("utf-8")

    def test_basic_parse_no_preamble(self):
        df = parse_sales_report_bytes(self._make_csv(0), "sales.csv")
        assert len(df) == 3
        assert "order_time" in df.columns
        assert "net_sales" in df.columns
        assert "product_name" in df.columns

    def test_parse_with_preamble(self):
        df = parse_sales_report_bytes(self._make_csv(2), "sales.csv")
        assert len(df) == 3

    def test_order_time_is_datetime(self):
        df = parse_sales_report_bytes(self._make_csv(0), "sales.csv")
        assert pd.api.types.is_datetime64_any_dtype(df["order_time"])

    def test_net_sales_is_numeric(self):
        df = parse_sales_report_bytes(self._make_csv(0), "sales.csv")
        assert pd.api.types.is_float_dtype(df["net_sales"])

    def test_net_sales_values_correct(self):
        df = parse_sales_report_bytes(self._make_csv(0), "sales.csv")
        assert df["net_sales"].tolist() == [90.0, 45.0, 35.0]

    def test_currency_string_parsed(self):
        # Currency value must be quoted in CSV to avoid comma splitting
        csv = (
            "Order ID,Order Time,Product Name,Net Sales\n"
            '1001,2025-03-01 10:00,Product A,"$1,234.56"\n'
        ).encode("utf-8")
        df = parse_sales_report_bytes(csv, "sales.csv")
        assert df["net_sales"].iloc[0] == pytest.approx(1234.56)

    def test_rows_without_order_time_dropped(self):
        csv = (
            "Order ID,Order Time,Product Name,Net Sales\n"
            "1001,2025-03-01 10:00,Product A,45.00\n"
            "1002,,Product B,30.00\n"  # missing order_time → dropped
        ).encode("utf-8")
        df = parse_sales_report_bytes(csv, "sales.csv")
        assert len(df) == 1

    def test_total_rows_dropped(self):
        csv = (
            "Order ID,Order Time,Product Name,Net Sales\n"
            "1001,2025-03-01 10:00,Product A,45.00\n"
            ",,Total,75.00\n"
        ).encode("utf-8")
        # "Total" rows should be filtered because product_name == "total"
        df = parse_sales_report_bytes(csv, "sales.csv")
        # Total row has no order_time so it's already dropped by that filter
        assert len(df) == 1
        assert df["product_name"].iloc[0] == "Product A"


# ===========================================================================
# compute_delivery_kpis
# ===========================================================================

class TestComputeDeliveryKPIs:
    def _make_sales_df(self, delivery_dt: pd.Timestamp) -> pd.DataFrame:
        """
        Create a sales DataFrame spanning 30 days around delivery_dt.
        Before: 14 days, $100/day.
        After:  14 days, $150/day (spike).
        Delivered product: 'Blue Dream 3.5g' (50% of each day's revenue).
        """
        rows = []
        for offset in range(-14, 14):
            day = delivery_dt + timedelta(days=offset)
            # Two line items per day
            rows.append({
                "order_id": f"O{offset}_A",
                "order_time": day,
                "product_name": "Blue Dream 3.5g",
                "net_sales": 50.0 if offset >= 0 else 30.0,
                "units_sold": 1.0,
            })
            rows.append({
                "order_id": f"O{offset}_B",
                "order_time": day,
                "product_name": "Sour Diesel",
                "net_sales": 70.0 if offset >= 0 else 70.0,
                "units_sold": 2.0,
            })
        return pd.DataFrame(rows)

    def test_net_sales_before(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis = compute_delivery_kpis(df, dt)
        # 14 days before × $100/day
        assert kpis["net_sales_before"] == pytest.approx(14 * 100.0)

    def test_net_sales_after(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis = compute_delivery_kpis(df, dt)
        # 14 days after × $120/day (50+70)
        assert kpis["net_sales_after"] == pytest.approx(14 * 120.0)

    def test_net_sales_lift_positive(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis = compute_delivery_kpis(df, dt)
        assert kpis["net_sales_lift_abs"] > 0
        assert kpis["net_sales_lift_pct"] > 0

    def test_orders_before_and_after(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis = compute_delivery_kpis(df, dt)
        # 14 days × 2 unique order_ids per day = 28
        assert kpis["orders_before"] == 28
        assert kpis["orders_after"] == 28

    def test_delivered_items_kpis(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis = compute_delivery_kpis(df, dt, delivered_names=["Blue Dream 3.5g"])
        # Before: 14 × $30 = $420; After: 14 × $50 = $700
        assert kpis["delivered_sales_before"] == pytest.approx(14 * 30.0)
        assert kpis["delivered_sales_after"] == pytest.approx(14 * 50.0)
        assert kpis["delivered_sales_lift_abs"] > 0

    def test_top_items_returned(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis = compute_delivery_kpis(
            df, dt, delivered_names=["Blue Dream 3.5g", "Sour Diesel"]
        )
        top = kpis["top_items"]
        assert not top.empty
        assert "item_name" in top.columns
        assert "sales_lift" in top.columns

    def test_no_data_in_window(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        # Sales all outside window
        df = pd.DataFrame([{
            "order_id": "O1",
            "order_time": pd.Timestamp("2020-01-01"),
            "product_name": "Product A",
            "net_sales": 100.0,
            "units_sold": 1.0,
        }])
        kpis = compute_delivery_kpis(df, dt)
        assert kpis["net_sales_before"] == 0.0
        assert kpis["net_sales_after"] == 0.0

    def test_custom_window_days(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        kpis_7 = compute_delivery_kpis(df, dt, window_days=7)
        kpis_14 = compute_delivery_kpis(df, dt, window_days=14)
        # 7-day window should give half the total
        assert kpis_7["net_sales_before"] == pytest.approx(kpis_14["net_sales_before"] / 2)


# ===========================================================================
# build_time_series
# ===========================================================================

class TestBuildTimeSeries:
    def _make_sales_df(self, delivery_dt: pd.Timestamp, days: int = 14) -> pd.DataFrame:
        rows = []
        for offset in range(-days, days):
            day = delivery_dt + timedelta(days=offset)
            rows.append({
                "order_id": f"O{offset}",
                "order_time": day,
                "product_name": "Blue Dream 3.5g",
                "net_sales": 100.0,
                "units_sold": 2.0,
            })
        return pd.DataFrame(rows)

    def test_daily_granularity(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        ts = build_time_series(df, dt, granularity="daily")
        assert "period" in ts.columns
        assert "total_net_sales" in ts.columns
        # 28 days total
        assert len(ts) == 28

    def test_hourly_granularity(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        # Create hourly data
        rows = []
        for h in range(-48, 48):
            rows.append({
                "order_id": f"O{h}",
                "order_time": dt + timedelta(hours=h),
                "product_name": "Blue Dream 3.5g",
                "net_sales": 10.0,
                "units_sold": 1.0,
            })
        df = pd.DataFrame(rows)
        ts = build_time_series(df, dt, window_days=2, granularity="hourly")
        assert len(ts) > 0
        # Should have multiple hours per day
        assert len(ts) > 4

    def test_delivered_columns_present(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        ts = build_time_series(df, dt, delivered_names=["Blue Dream 3.5g"])
        assert "delivered_net_sales" in ts.columns
        assert "non_delivered_net_sales" in ts.columns

    def test_no_data_returns_empty(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = pd.DataFrame(columns=["order_id", "order_time", "product_name", "net_sales", "units_sold"])
        ts = build_time_series(df, dt)
        assert ts.empty

    def test_total_equals_delivered_plus_non_delivered(self):
        dt = pd.Timestamp("2025-03-15 12:00")
        df = self._make_sales_df(dt)
        ts = build_time_series(df, dt, delivered_names=["Blue Dream 3.5g"])
        for _, row in ts.iterrows():
            assert row["total_net_sales"] == pytest.approx(
                row["delivered_net_sales"] + row["non_delivered_net_sales"]
            )
