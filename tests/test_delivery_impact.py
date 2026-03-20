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
    _rows_to_items_df,
    _parse_items_from_text,
    parse_manifest_pdf_bytes,
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


# ===========================================================================
# _rows_to_items_df  – PDF table parsing
# ===========================================================================

class TestRowsToItemsDf:
    """Tests for the pdfplumber table-row parser."""

    # ── helpers ─────────────────────────────────────────────────────────────
    def _header(self):
        return ["Line", "Item Name", "Ordered Qty", "Received Qty", "Unit Price"]

    # ── column-aware path (header row present) ───────────────────────────────
    def test_header_detects_name_and_received_qty(self):
        rows = [
            self._header(),
            ["1", "Eleven Flower .75+", "25", "25", "$12.00"],
        ]
        df = _rows_to_items_df(rows, "")
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Eleven Flower .75+"
        assert df.iloc[0]["qty"] == pytest.approx(25.0)

    def test_received_qty_preferred_over_ordered(self):
        # Ordered qty != received qty; parser must pick Received Qty column.
        rows = [
            self._header(),
            ["1", "Eleven Flower .75+", "30", "25", "$12.00"],
        ]
        df = _rows_to_items_df(rows, "")
        assert df.iloc[0]["qty"] == pytest.approx(25.0)

    def test_line_number_not_taken_as_qty(self):
        # Without the fix, line number "1" would become qty.
        rows = [
            self._header(),
            ["1", "Eleven Flower .75+", "25", "25", "$12.00"],
            ["2", "Natural Selection Live Resin Diamonds and Sauce", "50", "50", "$18.00"],
        ]
        df = _rows_to_items_df(rows, "")
        assert list(df["qty"]) == [25.0, 50.0]

    def test_currency_cells_not_in_product_name(self):
        rows = [
            self._header(),
            ["1", "Eleven Flower .75+", "25", "25", "$12.00"],
        ]
        df = _rows_to_items_df(rows, "")
        assert "$" not in df.iloc[0]["item_name"]

    def test_multiple_items(self):
        rows = [
            self._header(),
            ["1", "Eleven Flower .75+", "25", "25", "$12.00"],
            ["2", "Natural Selection Live Resin Diamonds and Sauce", "50", "50", "$18.00"],
            ["3", "Blue Dream 3.5g", "10", "10", "$9.00"],
        ]
        df = _rows_to_items_df(rows, "")
        assert len(df) == 3
        assert list(df["item_name"]) == [
            "Eleven Flower .75+",
            "Natural Selection Live Resin Diamonds and Sauce",
            "Blue Dream 3.5g",
        ]
        assert list(df["qty"]) == [25.0, 50.0, 10.0]

    # ── multi-line cell support ──────────────────────────────────────────────
    def test_multiline_cell_joined_with_space(self):
        rows = [
            ["Line", "Item Name", "Received Qty"],
            ["1", "Natural Selection Live Resin\nDiamonds and Sauce", "50"],
        ]
        df = _rows_to_items_df(rows, "")
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Natural Selection Live Resin Diamonds and Sauce"
        assert df.iloc[0]["qty"] == pytest.approx(50.0)

    # ── continuation rows (name wraps to the next table row) ────────────────
    def test_continuation_row_appended_to_previous_item(self):
        rows = [
            ["Line", "Item Name", "Received Qty"],
            ["1", "Natural Selection Live Resin Diamonds", "50"],
            ["", "and Sauce", ""],
            ["2", "Blue Dream 3.5g", "30"],
        ]
        df = _rows_to_items_df(rows, "")
        assert "Natural Selection Live Resin Diamonds and Sauce" in list(df["item_name"])
        assert "Blue Dream 3.5g" in list(df["item_name"])
        # Continuation text must NOT bleed into the next item's name
        blue_dream_row = df[df["item_name"] == "Blue Dream 3.5g"]
        assert len(blue_dream_row) == 1

    def test_continuation_does_not_corrupt_next_item_qty(self):
        rows = [
            ["Line", "Item Name", "Received Qty"],
            ["1", "Item A First Line", "25"],
            ["", "Item A Second Line", ""],
            ["2", "Item B", "40"],
        ]
        df = _rows_to_items_df(rows, "")
        item_a = df[df["item_name"].str.startswith("Item A")]
        item_b = df[df["item_name"] == "Item B"]
        assert len(item_a) == 1
        assert len(item_b) == 1
        assert item_a.iloc[0]["qty"] == pytest.approx(25.0)
        assert item_b.iloc[0]["qty"] == pytest.approx(40.0)

    # ── heuristic path (no header detected) ─────────────────────────────────
    def test_heuristic_skips_currency_cells(self):
        # No header – heuristic path; $ cells should not appear in name.
        rows = [
            ["1", "Blue Dream 3.5g", "30", "$9.00"],
            ["2", "Sour Diesel", "20", "$8.00"],
        ]
        df = _rows_to_items_df(rows, "")
        for name in df["item_name"]:
            assert "$" not in name

    def test_heuristic_last_numeric_is_qty(self):
        # Line number "1" is first; last numeric "25" should be qty.
        rows = [
            ["1", "Eleven Flower .75+", "25"],
            ["2", "Sour Diesel", "50"],
        ]
        df = _rows_to_items_df(rows, "")
        assert list(df["qty"]) == [25.0, 50.0]

    # ── edge cases ───────────────────────────────────────────────────────────
    def test_empty_rows_returns_text_fallback_or_empty(self):
        df = _rows_to_items_df([], "")
        assert isinstance(df, pd.DataFrame)
        assert "item_name" in df.columns
        assert "qty" in df.columns

    def test_single_column_falls_back(self):
        rows = [["only one cell"]]
        df = _rows_to_items_df(rows, "")
        assert isinstance(df, pd.DataFrame)

    def test_header_skipped_in_data(self):
        # Repeated header rows mid-table should not create spurious items.
        rows = [
            ["Line", "Item Name", "Received Qty"],
            ["1", "Eleven Flower .75+", "25"],
            ["Line", "Item Name", "Received Qty"],  # repeated header
            ["2", "Blue Dream", "30"],
        ]
        df = _rows_to_items_df(rows, "")
        assert len(df) == 2


# ===========================================================================
# _parse_items_from_text  – text-based fallback parser
# ===========================================================================

class TestParseItemsFromText:
    """Tests for the raw-text fallback item parser."""

    def test_single_item(self):
        df = _parse_items_from_text("Eleven Flower .75+ 25")
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Eleven Flower .75+"
        assert df.iloc[0]["qty"] == pytest.approx(25.0)

    def test_multiple_single_line_items(self):
        text = "Eleven Flower .75+ 25\nBlue Dream 3.5g 30\nSour Diesel 10"
        df = _parse_items_from_text(text)
        assert len(df) == 3
        assert list(df["qty"]) == [25.0, 30.0, 10.0]

    def test_multiline_product_name_joined(self):
        text = (
            "Natural Selection Live Resin Diamonds\n"
            "and Sauce 50"
        )
        df = _parse_items_from_text(text)
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Natural Selection Live Resin Diamonds and Sauce"
        assert df.iloc[0]["qty"] == pytest.approx(50.0)

    def test_multiline_name_then_single_line_item(self):
        text = (
            "Eleven Flower .75+ 25\n"
            "Natural Selection Live Resin Diamonds\n"
            "and Sauce 50\n"
            "Blue Dream 3.5g 30"
        )
        df = _parse_items_from_text(text)
        assert len(df) == 3
        assert df.iloc[0]["item_name"] == "Eleven Flower .75+"
        assert df.iloc[1]["item_name"] == "Natural Selection Live Resin Diamonds and Sauce"
        assert df.iloc[2]["item_name"] == "Blue Dream 3.5g"

    def test_blank_line_resets_accumulator(self):
        # Blank line between two fragments should not join them.
        text = (
            "Random orphan text\n"
            "\n"
            "Eleven Flower .75+ 25"
        )
        df = _parse_items_from_text(text)
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Eleven Flower .75+"

    def test_header_keywords_not_included_in_name(self):
        text = "Item\nEleven Flower .75+ 25"
        df = _parse_items_from_text(text)
        assert "item" not in df.iloc[0]["item_name"].lower()

    def test_skip_date_like_lines(self):
        # "03/15/2025" followed by a number should not be captured as an item.
        text = "03/15/2025 14:32\nEleven Flower .75+ 25"
        df = _parse_items_from_text(text)
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Eleven Flower .75+"

    def test_empty_text_returns_empty_df(self):
        df = _parse_items_from_text("")
        assert df.empty
        assert "item_name" in df.columns
        assert "qty" in df.columns

    def test_fractional_quantities(self):
        df = _parse_items_from_text("CBD Tincture 500mg 2.5")
        assert df.iloc[0]["qty"] == pytest.approx(2.5)


# ===========================================================================
# parse_manifest_pdf_bytes  – integration smoke test (no real PDF required)
# ===========================================================================

class TestParseManifestPdfBytesSmoke:
    """
    Lightweight integration tests that verify parse_manifest_pdf_bytes returns
    the expected (received_dt, items_df, raw_text) tuple contract without
    needing an actual PDF file on disk.
    """

    def test_invalid_bytes_returns_empty(self):
        received_dt, items_df, raw_text = parse_manifest_pdf_bytes(b"not a pdf")
        # Should not raise; returns graceful empty result.
        assert items_df is not None
        assert "item_name" in items_df.columns
        assert "qty" in items_df.columns

    def test_return_type_contract(self):
        received_dt, items_df, raw_text = parse_manifest_pdf_bytes(b"")
        assert received_dt is None or isinstance(received_dt, pd.Timestamp)
        assert isinstance(items_df, pd.DataFrame)
        assert isinstance(raw_text, str)
