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
    build_wow_time_series,
    compute_delivery_kpis,
    compute_weekday_wow_kpis,
    find_sales_header_row,
    match_manifest_to_sales,
    normalize_product_name,
    parse_sales_report_bytes,
    parse_manifest_csv_xlsx_bytes,
    _rows_to_items_df,
    _parse_items_from_text,
    parse_manifest_pdf_bytes,
    _parse_datetime_string,
    _extract_received_dt_from_rows,
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


# ===========================================================================
# parse_manifest_csv_xlsx_bytes  – CSV/XLSX manifest parser
# ===========================================================================

import os as _os
import pathlib as _pathlib

_FIXTURE_DIR = _pathlib.Path(_os.path.dirname(__file__)) / "fixtures"
_CRESCO_CSV = _FIXTURE_DIR / "cresco031926.csv"


class TestParseManifestCsvXlsxBytes:
    """Tests for the Dutchie-style CSV/XLSX manifest parser."""

    # ── helper builders ──────────────────────────────────────────────────────

    def _simple_csv(self, rows: list[list[str]]) -> bytes:
        """Build minimal CSV bytes from a list of rows (list of cells)."""
        lines = [",".join(r) for r in rows]
        return "\n".join(lines).encode("utf-8")

    # ── return-type contract ─────────────────────────────────────────────────

    def test_return_type_contract(self):
        received_dt, items_df, raw_text = parse_manifest_csv_xlsx_bytes(b"", filename="m.csv")
        assert received_dt is None or isinstance(received_dt, pd.Timestamp)
        assert isinstance(items_df, pd.DataFrame)
        assert isinstance(raw_text, str)

    def test_invalid_bytes_returns_empty_gracefully(self):
        received_dt, items_df, raw_text = parse_manifest_csv_xlsx_bytes(
            b"\x00\xff\xfe", filename="m.csv"
        )
        assert "item_name" in items_df.columns
        assert "qty" in items_df.columns

    # ── basic single-row items ───────────────────────────────────────────────

    def test_simple_single_item(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Blue Dream 3.5g"
        assert df.iloc[0]["qty"] == pytest.approx(10.0)

    def test_simple_multiple_items(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
            ["Sour Diesel", "5"],
            ["OG Kush 7g", "3"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 3
        assert list(df["item_name"]) == ["Blue Dream 3.5g", "Sour Diesel", "OG Kush 7g"]
        assert list(df["qty"]) == [10.0, 5.0, 3.0]

    # ── preamble metadata rows skipped ──────────────────────────────────────

    def test_preamble_rows_skipped(self):
        csv = self._simple_csv([
            ["Manifest #", "cresco031926"],
            ["Received Date", "03/19/2026"],
            ["Vendor", "Cresco Illinois"],
            [""],
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Blue Dream 3.5g"

    # ── received date extraction ─────────────────────────────────────────────

    def test_received_date_extracted_from_preamble(self):
        csv = self._simple_csv([
            ["Received Date", "03/19/2026 10:30"],
            ["Vendor", "Cresco Illinois"],
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
        ])
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert received_dt is not None
        assert isinstance(received_dt, pd.Timestamp)
        assert received_dt.month == 3
        assert received_dt.day == 19

    # ── repeated header rows mid-file ────────────────────────────────────────

    def test_repeated_header_rows_skipped(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
            ["Product", "Quantity"],  # repeated header – must not become an item
            ["Sour Diesel", "5"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 2
        names = list(df["item_name"])
        assert "Blue Dream 3.5g" in names
        assert "Sour Diesel" in names
        # "Product" must not appear as an item name
        for n in names:
            assert n.lower() != "product"

    # ── continuation rows (multi-line product name) ──────────────────────────

    def test_continuation_rows_joined(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Cresco", ""],
            ["Rest", ""],
            ["Flower", ""],
            ["3.5g- The", ""],
            ["4th Kind", "3"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 1
        assert df.iloc[0]["item_name"] == "Cresco Rest Flower 3.5g- The 4th Kind"
        assert df.iloc[0]["qty"] == pytest.approx(3.0)

    def test_two_multi_fragment_products(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["High", ""],
            ["Supply Hybrid Flower 7g-", ""],
            ["Banana Cream Cake", "5"],
            ["Blue Dream 3.5g", "10"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 2
        assert df.iloc[0]["item_name"] == "High Supply Hybrid Flower 7g- Banana Cream Cake"
        assert df.iloc[0]["qty"] == pytest.approx(5.0)
        assert df.iloc[1]["item_name"] == "Blue Dream 3.5g"
        assert df.iloc[1]["qty"] == pytest.approx(10.0)

    def test_continuation_does_not_bleed_into_next_item(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Fragment A", ""],
            ["Fragment B", "2"],
            ["Standalone Item", "7"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert len(df) == 2
        assert df.iloc[1]["item_name"] == "Standalone Item"
        assert df.iloc[1]["qty"] == pytest.approx(7.0)
        # Fragment text must not appear in standalone item's name
        assert "Fragment" not in df.iloc[1]["item_name"]

    # ── quoted cells with embedded newlines ──────────────────────────────────

    def test_quoted_cell_with_embedded_newline(self):
        # CSV standard: newlines inside quoted fields are preserved by pandas.
        csv_text = (
            "Product,Quantity\n"
            '"Garden Society Sativa Flower 14g\n- Lemon Meringue",2\n'
        )
        raw = csv_text.encode("utf-8")
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="m.csv")
        assert len(df) == 1
        name = df.iloc[0]["item_name"]
        # Should have been collapsed to a single line.
        assert "\n" not in name
        assert "Garden Society" in name
        assert "Lemon Meringue" in name

    # ── preferred received-qty column selection ───────────────────────────────

    def test_received_qty_preferred_over_plain_qty(self):
        csv = self._simple_csv([
            ["Product", "Ordered Qty", "Received Qty"],
            ["Blue Dream 3.5g", "15", "10"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert df.iloc[0]["qty"] == pytest.approx(10.0)

    # ── optional columns retained ────────────────────────────────────────────

    def test_optional_columns_retained(self):
        csv = self._simple_csv([
            ["Product", "Quantity", "Package ID", "Batch", "License Number", "Location"],
            ["Blue Dream 3.5g", "10", "PKG-001", "BATCH-001", "LIC-001", "LOC-A"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert "package_id" in df.columns
        assert df.iloc[0]["package_id"] == "PKG-001"
        assert "batch" in df.columns
        assert df.iloc[0]["batch"] == "BATCH-001"

    # ── cresco031926.csv fixture ─────────────────────────────────────────────

    def test_cresco_fixture_item_count(self):
        """The fixture has 5 distinct items."""
        raw = _CRESCO_CSV.read_bytes()
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        assert len(df) == 5

    def test_cresco_fixture_reconstructed_names(self):
        raw = _CRESCO_CSV.read_bytes()
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        names = list(df["item_name"])
        assert "Cresco Rest Flower 3.5g- The 4th Kind" in names
        assert "High Supply Hybrid Flower 7g- Banana Cream Cake" in names

    def test_cresco_fixture_quantities_numeric(self):
        raw = _CRESCO_CSV.read_bytes()
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        assert pd.api.types.is_float_dtype(df["qty"]) or pd.api.types.is_integer_dtype(df["qty"])
        assert (df["qty"] > 0).all()

    def test_cresco_fixture_no_header_in_items(self):
        raw = _CRESCO_CSV.read_bytes()
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        for name in df["item_name"]:
            assert name.lower() not in {"product", "quantity", "item"}

    def test_cresco_fixture_received_date_extracted(self):
        raw = _CRESCO_CSV.read_bytes()
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        assert received_dt is not None
        assert received_dt.month == 3
        assert received_dt.day == 19
        assert received_dt.year == 2026


# ===========================================================================
# _parse_datetime_string  – explicit-format datetime parser
# ===========================================================================

class TestParseDatetimeString:
    """Tests for the explicit-format datetime parser."""

    def test_mdy_hm_format(self):
        ts = _parse_datetime_string("03/19/2026 10:30")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 3
        assert ts.day == 19
        assert ts.hour == 10
        assert ts.minute == 30

    def test_mdy_hm_am_pm_format(self):
        ts = _parse_datetime_string("03/19/2026 10:58 AM")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 3
        assert ts.day == 19
        assert ts.hour == 10
        assert ts.minute == 58

    def test_mdy_hm_pm_format(self):
        ts = _parse_datetime_string("03/19/2026 02:30 PM")
        assert ts is not None
        assert ts.hour == 14

    def test_mdy_two_digit_year(self):
        ts = _parse_datetime_string("03/19/26 10:58 AM")
        assert ts is not None
        assert ts.month == 3
        assert ts.day == 19

    def test_iso_datetime(self):
        ts = _parse_datetime_string("2026-03-19T10:30:00")
        assert ts is not None
        assert ts.year == 2026

    def test_iso_date_only(self):
        ts = _parse_datetime_string("2026-03-19")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 3
        assert ts.day == 19

    def test_empty_string_returns_none(self):
        assert _parse_datetime_string("") is None

    def test_non_date_string_returns_none(self):
        assert _parse_datetime_string("not a date") is None

    def test_returns_timezone_naive(self):
        ts = _parse_datetime_string("03/19/2026 10:30")
        assert ts is not None
        assert ts.tzinfo is None


# ===========================================================================
# _extract_received_dt_from_rows  – priority-ranked date extraction
# ===========================================================================

class TestExtractReceivedDtFromRows:
    """Tests for priority-ranked received date extraction."""

    def test_labeled_row_takes_priority(self):
        # "Received Date" label should win over any earlier date in raw text.
        rows = [
            ["Manifest #", "cresco031926"],
            ["Received Date", "03/19/2026 10:58 AM"],
            ["Vendor", "Cresco Illinois"],
        ]
        dt = _extract_received_dt_from_rows(rows, "")
        assert dt is not None
        assert dt.month == 3
        assert dt.day == 19
        assert dt.year == 2026
        assert dt.hour == 10

    def test_date_received_label_variant(self):
        rows = [
            ["Date Received", "03/19/2026 10:30"],
        ]
        dt = _extract_received_dt_from_rows(rows, "")
        assert dt is not None
        assert dt.day == 19

    def test_received_label_variant(self):
        rows = [
            ["Received", "03/19/2026 10:30"],
        ]
        dt = _extract_received_dt_from_rows(rows, "")
        assert dt is not None
        assert dt.day == 19

    def test_falls_back_to_preamble_scan(self):
        # No labeled row, but a date appears in the preamble text.
        rows = [
            ["Vendor", "Cresco Illinois"],
            ["Export", "03/19/2026 10:30"],
        ]
        dt = _extract_received_dt_from_rows(rows, "")
        assert dt is not None
        assert dt.day == 19

    def test_falls_back_to_raw_text(self):
        # No useful rows; date in raw_text fallback.
        rows: list = []
        dt = _extract_received_dt_from_rows(rows, "Delivery on 03/19/2026 10:30")
        assert dt is not None
        assert dt.day == 19

    def test_no_date_returns_none(self):
        rows = [["Vendor", "Cresco Illinois"]]
        dt = _extract_received_dt_from_rows(rows, "no date here")
        assert dt is None

    def test_labeled_row_preferred_over_raw_text_date(self):
        # raw_text has an earlier date (01/01/2020) but labeled row has the real one.
        rows = [
            ["Received Date", "03/19/2026 10:30"],
        ]
        dt = _extract_received_dt_from_rows(rows, "Some date 01/01/2020 09:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3


# ===========================================================================
# Type coercion guarantees in parse_manifest_csv_xlsx_bytes
# ===========================================================================

class TestManifestTypeCoercions:
    """Verify item_name is always str and qty is always numeric."""

    def _simple_csv(self, rows: list[list[str]]) -> bytes:
        lines = [",".join(r) for r in rows]
        return "\n".join(lines).encode("utf-8")

    def test_item_name_is_always_str(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
            ["Sour Diesel", "5"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        for val in df["item_name"]:
            assert isinstance(val, str), f"Expected str, got {type(val)}"

    def test_qty_is_always_numeric(self):
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
            ["Sour Diesel", "5"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        assert pd.api.types.is_numeric_dtype(df["qty"])

    def test_qty_sum_does_not_raise(self):
        """qty.sum() must not raise – the original int+str bug trigger."""
        csv = self._simple_csv([
            ["Product", "Quantity"],
            ["Blue Dream 3.5g", "10"],
            ["Sour Diesel", "5"],
        ])
        _, df, _ = parse_manifest_csv_xlsx_bytes(csv, filename="m.csv")
        total = df["qty"].sum()  # must not raise
        assert total == pytest.approx(15.0)

    def test_cresco_fixture_item_name_dtype_str(self):
        raw = _CRESCO_CSV.read_bytes()
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        for val in df["item_name"]:
            assert isinstance(val, str)

    def test_cresco_fixture_qty_dtype_numeric(self):
        raw = _CRESCO_CSV.read_bytes()
        _, df, _ = parse_manifest_csv_xlsx_bytes(raw, filename="cresco031926.csv")
        assert pd.api.types.is_numeric_dtype(df["qty"])
        # Quantities should be > 0 for all items in the fixture.
        assert (df["qty"] > 0).all()

# ===========================================================================
# compute_weekday_wow_kpis  – week-over-week same-weekday comparison
# ===========================================================================

class TestComputeWeekdayWowKpis:
    """Tests for the same-weekday week-over-week KPI function."""

    _DELIVERY_DT = pd.Timestamp("2026-03-19")  # Thursday

    def _make_sales_df(self, rows):
        """Build a minimal sales DataFrame from a list of (order_time, net_sales, product_name) tuples."""
        data = []
        for i, (dt, ns, pn) in enumerate(rows):
            data.append({
                "order_id": f"ORD{i:04d}",
                "order_time": pd.Timestamp(dt),
                "product_name": pn,
                "net_sales": float(ns),
                "units_sold": 1.0,
            })
        return pd.DataFrame(data)

    def test_thursday_compares_to_thursday_minus_7(self):
        """Delivery on Thu 2026-03-19 must compare to Thu 2026-03-12."""
        sales = self._make_sales_df([
            # delivery day (Thu 03-19)
            ("2026-03-19 10:00", 100.0, "Blue Dream"),
            ("2026-03-19 14:00", 200.0, "Blue Dream"),
            # prior week same weekday (Thu 03-12)
            ("2026-03-12 11:00", 80.0, "Blue Dream"),
        ])
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        assert result["net_sales_before"] == pytest.approx(80.0)
        assert result["net_sales_after"] == pytest.approx(300.0)
        assert result["net_sales_lift_abs"] == pytest.approx(220.0)

    def test_prior_day_start_is_7_days_before_delivery(self):
        """prior_day_start must be exactly delivery_day_start - 7 days."""
        sales = self._make_sales_df([("2026-03-19 10:00", 50.0, "A")])
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        expected_delivery = pd.Timestamp("2026-03-19")
        expected_prior = pd.Timestamp("2026-03-12")
        assert result["delivery_day_start"] == expected_delivery
        assert result["prior_day_start"] == expected_prior

    def test_no_data_prior_week_pct_lift_is_nan(self):
        """When prior week has no sales, percent lift must be NaN (not raise)."""
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 150.0, "Blue Dream"),
        ])
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        assert result["net_sales_before"] == pytest.approx(0.0)
        assert result["net_sales_after"] == pytest.approx(150.0)
        # Percent lift is undefined (0 baseline) – must be NaN, not raise
        assert pd.isna(result["net_sales_lift_pct"])

    def test_no_data_delivery_day(self):
        """When delivery day has no sales, lift should be negative."""
        sales = self._make_sales_df([
            ("2026-03-12 10:00", 120.0, "Blue Dream"),
        ])
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        assert result["net_sales_before"] == pytest.approx(120.0)
        assert result["net_sales_after"] == pytest.approx(0.0)
        assert result["net_sales_lift_abs"] == pytest.approx(-120.0)

    def test_delivered_items_subset_metrics(self):
        """Delivered-items sub-metrics must match the subset filtered by name."""
        sales = self._make_sales_df([
            # delivery day
            ("2026-03-19 10:00", 100.0, "Blue Dream"),
            ("2026-03-19 11:00", 50.0, "Sour Diesel"),  # non-delivered
            # prior week
            ("2026-03-12 10:00", 60.0, "Blue Dream"),
            ("2026-03-12 11:00", 40.0, "Sour Diesel"),
        ])
        result = compute_weekday_wow_kpis(
            sales, self._DELIVERY_DT, delivered_names=["Blue Dream"]
        )
        # delivered subset: prior=60, delivery=100
        assert result["delivered_sales_before"] == pytest.approx(60.0)
        assert result["delivered_sales_after"] == pytest.approx(100.0)
        assert result["delivered_sales_lift_abs"] == pytest.approx(40.0)
        # total must include all products
        assert result["net_sales_before"] == pytest.approx(100.0)
        assert result["net_sales_after"] == pytest.approx(150.0)

    def test_orders_count_uses_unique_order_ids(self):
        """Order count must be distinct order IDs per day."""
        data = [
            # delivery day – 2 distinct orders, 3 rows
            {"order_id": "A", "order_time": pd.Timestamp("2026-03-19 09:00"),
             "product_name": "X", "net_sales": 10.0, "units_sold": 1.0},
            {"order_id": "A", "order_time": pd.Timestamp("2026-03-19 09:00"),
             "product_name": "Y", "net_sales": 5.0, "units_sold": 1.0},
            {"order_id": "B", "order_time": pd.Timestamp("2026-03-19 10:00"),
             "product_name": "X", "net_sales": 8.0, "units_sold": 1.0},
            # prior week – 1 order
            {"order_id": "C", "order_time": pd.Timestamp("2026-03-12 09:00"),
             "product_name": "X", "net_sales": 7.0, "units_sold": 1.0},
        ]
        sales = pd.DataFrame(data)
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        assert result["orders_after"] == 2
        assert result["orders_before"] == 1

    def test_top_items_returned_when_delivered_names_provided(self):
        """top_items DataFrame must be non-empty when delivered_names provided."""
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 100.0, "Blue Dream"),
            ("2026-03-12 10:00", 60.0, "Blue Dream"),
        ])
        result = compute_weekday_wow_kpis(
            sales, self._DELIVERY_DT, delivered_names=["Blue Dream"]
        )
        assert not result["top_items"].empty
        row = result["top_items"].iloc[0]
        assert row["item_name"] == "Blue Dream"
        assert row["sales_lift"] == pytest.approx(40.0)

    def test_empty_sales_df_returns_zero_kpis(self):
        """Empty sales DataFrame must not raise and must return zero/NaN KPIs."""
        sales = pd.DataFrame(columns=["order_id", "order_time", "product_name",
                                       "net_sales", "units_sold"])
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        assert result["net_sales_before"] == pytest.approx(0.0)
        assert result["net_sales_after"] == pytest.approx(0.0)
        assert pd.isna(result["net_sales_lift_pct"])

    def test_sales_outside_window_excluded(self):
        """Sales from days other than the delivery day or prior-week same day must be excluded."""
        sales = self._make_sales_df([
            # delivery day – in window
            ("2026-03-19 10:00", 100.0, "Blue Dream"),
            # day after delivery – must be excluded
            ("2026-03-20 10:00", 999.0, "Blue Dream"),
            # prior week same day – in window
            ("2026-03-12 10:00", 50.0, "Blue Dream"),
            # two weeks prior – must be excluded
            ("2026-03-05 10:00", 999.0, "Blue Dream"),
        ])
        result = compute_weekday_wow_kpis(sales, self._DELIVERY_DT)
        assert result["net_sales_before"] == pytest.approx(50.0)
        assert result["net_sales_after"] == pytest.approx(100.0)


# ===========================================================================
# build_wow_time_series  – two-series chart data for WoW overlay
# ===========================================================================

class TestBuildWowTimeSeries:
    """Tests for the week-over-week time-series builder."""

    _DELIVERY_DT = pd.Timestamp("2026-03-19")

    def _make_sales_df(self, rows):
        data = []
        for i, (dt, ns, pn) in enumerate(rows):
            data.append({
                "order_id": f"ORD{i:04d}",
                "order_time": pd.Timestamp(dt),
                "product_name": pn,
                "net_sales": float(ns),
                "units_sold": 1.0,
            })
        return pd.DataFrame(data)

    def test_returns_two_dataframes(self):
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 100.0, "A"),
            ("2026-03-12 10:00", 80.0, "A"),
        ])
        delivery_ts, prior_ts = build_wow_time_series(sales, self._DELIVERY_DT)
        assert isinstance(delivery_ts, pd.DataFrame)
        assert isinstance(prior_ts, pd.DataFrame)

    def test_delivery_ts_contains_delivery_day_data(self):
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 100.0, "A"),
            ("2026-03-12 10:00", 80.0, "A"),
        ])
        delivery_ts, _ = build_wow_time_series(sales, self._DELIVERY_DT)
        assert not delivery_ts.empty
        assert delivery_ts["total_net_sales"].sum() == pytest.approx(100.0)

    def test_prior_ts_period_shifted_forward_7_days(self):
        """prior_ts period values must be shifted +7 days so x-axes align."""
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 100.0, "A"),
            ("2026-03-12 10:00", 80.0, "A"),
        ])
        delivery_ts, prior_ts = build_wow_time_series(sales, self._DELIVERY_DT)
        # Prior-week data (03-12) should be shifted to 03-19
        assert not prior_ts.empty
        # After shifting, the period date should be 2026-03-19
        assert prior_ts.iloc[0]["period"].date() == pd.Timestamp("2026-03-19").date()

    def test_empty_prior_week_returns_empty_prior_ts(self):
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 100.0, "A"),
        ])
        _, prior_ts = build_wow_time_series(sales, self._DELIVERY_DT)
        assert prior_ts.empty

    def test_columns_match_build_time_series_schema(self):
        sales = self._make_sales_df([
            ("2026-03-19 10:00", 100.0, "A"),
            ("2026-03-12 10:00", 80.0, "A"),
        ])
        delivery_ts, prior_ts = build_wow_time_series(sales, self._DELIVERY_DT)
        expected_cols = {"period", "total_net_sales", "delivered_net_sales",
                         "non_delivered_net_sales", "order_count"}
        assert expected_cols.issubset(set(delivery_ts.columns))
        assert expected_cols.issubset(set(prior_ts.columns))

    def test_string_order_time_does_not_raise(self):
        """build_wow_time_series must not raise when order_time is object/string dtype."""
        data = [
            {"order_id": "ORD0001", "order_time": "2026-03-19 10:00",
             "product_name": "A", "net_sales": 100.0, "units_sold": 1.0},
            {"order_id": "ORD0002", "order_time": "2026-03-12 10:00",
             "product_name": "A", "net_sales": 80.0, "units_sold": 1.0},
        ]
        sales = pd.DataFrame(data)
        # Force order_time to object dtype to simulate unparsed string input
        sales["order_time"] = sales["order_time"].astype(object)
        assert sales["order_time"].dtype == object
        # Should not raise "unsupported operand type(s) for +: 'int' and 'str'"
        delivery_ts, prior_ts = build_wow_time_series(sales, self._DELIVERY_DT)
        assert not delivery_ts.empty
        assert not prior_ts.empty
        # Prior period must be shifted to delivery day date
        assert prior_ts.iloc[0]["period"].date() == pd.Timestamp("2026-03-19").date()


# ===========================================================================
# Dtype-coercion regression tests (guards against int+str errors in plots)
# ===========================================================================

class TestCoerceTsFrameForPlot:
    """
    Tests for the dtype-coercion behaviour that must be applied to any time-series
    frame before it is handed to Plotly.  The actual helper (_coerce_ts_frame_for_plot)
    lives in app.py, so we test the equivalent logic inline here to validate that
    the underlying functions (build_time_series / build_wow_time_series) produce
    data that, once coerced, satisfies the Plotly safety contract.
    """

    # Re-implement the same coercion the helper applies so we can test it.
    @staticmethod
    def _coerce(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df["period"] = pd.to_datetime(df["period"], errors="coerce")
        df = df.dropna(subset=["period"])
        for col in ("total_net_sales", "delivered_net_sales",
                    "non_delivered_net_sales", "order_count"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    def _make_mixed_frame(self) -> pd.DataFrame:
        """Build a frame that intentionally has object-dtype columns to simulate
        the failure mode that caused 'unsupported operand type(s) for +: int and str'."""
        return pd.DataFrame({
            "period": ["2026-03-19", "2026-03-20"],
            "total_net_sales": ["100", "200"],        # strings – must be coerced
            "delivered_net_sales": [50, "75"],         # mixed  – must be coerced
            "non_delivered_net_sales": [50.0, 125.0],
            "order_count": ["3", "5"],                 # strings – must be coerced
        })

    def test_coerce_period_to_datetime(self):
        df = self._coerce(self._make_mixed_frame())
        assert pd.api.types.is_datetime64_any_dtype(df["period"])

    def test_coerce_total_net_sales_to_float(self):
        df = self._coerce(self._make_mixed_frame())
        assert pd.api.types.is_numeric_dtype(df["total_net_sales"])
        assert list(df["total_net_sales"]) == [100, 200]

    def test_coerce_delivered_net_sales_mixed(self):
        df = self._coerce(self._make_mixed_frame())
        assert pd.api.types.is_numeric_dtype(df["delivered_net_sales"])
        assert list(df["delivered_net_sales"]) == [50, 75]

    def test_coerce_order_count_to_float(self):
        df = self._coerce(self._make_mixed_frame())
        assert pd.api.types.is_numeric_dtype(df["order_count"])

    def test_nat_period_rows_dropped(self):
        df = pd.DataFrame({
            "period": ["2026-03-19", "not-a-date"],
            "total_net_sales": [100.0, 200.0],
        })
        df_coerced = self._coerce(df)
        assert len(df_coerced) == 1
        assert df_coerced["period"].iloc[0] == pd.Timestamp("2026-03-19")

    def test_empty_frame_returned_unchanged(self):
        empty = pd.DataFrame(columns=["period", "total_net_sales", "order_count"])
        result = self._coerce(empty)
        assert result.empty

    def test_build_time_series_output_safe_after_coerce(self):
        """build_time_series output must be safe after coercion (period is datetime, sales is float)."""
        sales = pd.DataFrame({
            "order_id": ["A", "B"],
            "order_time": pd.to_datetime(["2026-03-19 10:00", "2026-03-12 10:00"]),
            "product_name": ["X", "X"],
            "net_sales": [100.0, 80.0],
            "units_sold": [1.0, 1.0],
        })
        ts = build_time_series(sales, pd.Timestamp("2026-03-19"), window_days=14)
        ts_coerced = self._coerce(ts)
        assert pd.api.types.is_datetime64_any_dtype(ts_coerced["period"])
        assert pd.api.types.is_float_dtype(ts_coerced["total_net_sales"])

    def test_build_wow_time_series_output_safe_after_coerce(self):
        """build_wow_time_series output must be safe after coercion in both modes."""
        sales = pd.DataFrame({
            "order_id": ["A", "B"],
            "order_time": pd.to_datetime(["2026-03-19 10:00", "2026-03-12 10:00"]),
            "product_name": ["X", "X"],
            "net_sales": [100.0, 80.0],
            "units_sold": [1.0, 1.0],
        })
        deliv_ts, prior_ts = build_wow_time_series(sales, pd.Timestamp("2026-03-19"))
        for frame in (deliv_ts, prior_ts):
            coerced = self._coerce(frame)
            if not coerced.empty:
                assert pd.api.types.is_datetime64_any_dtype(coerced["period"])
                assert pd.api.types.is_float_dtype(coerced["total_net_sales"])


# ===========================================================================
# parse_manifest_csv_xlsx_bytes – received_dt Timestamp guarantee
# ===========================================================================

class TestManifestReceivedDtIsTimestamp:
    """Ensure parse_manifest_csv_xlsx_bytes always returns received_dt as
    pd.Timestamp (never a raw string), so downstream isoformat() / normalize()
    calls cannot cause a type error."""

    @staticmethod
    def _dutchie_csv(received_line: str) -> bytes:
        """Build a minimal Dutchie-style manifest CSV with a preamble date line."""
        lines = [
            f"Received Date/Time:,{received_line}",
            "Vendor:,Test Vendor",
            "",
            "Product,Quantity Received",
            "Blue Dream 3.5g,10",
            "Sour Diesel 1g,5",
        ]
        return "\n".join(lines).encode("utf-8")

    def test_received_dt_is_timestamp_for_standard_format(self):
        raw = self._dutchie_csv("03/19/2026 10:58 AM")
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(raw, filename="test.csv")
        assert received_dt is not None, "received_dt must not be None for a parseable date"
        assert isinstance(received_dt, pd.Timestamp), (
            f"received_dt must be pd.Timestamp, got {type(received_dt)}"
        )

    def test_received_dt_correct_value(self):
        raw = self._dutchie_csv("03/19/2026 10:58 AM")
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(raw, filename="test.csv")
        assert received_dt is not None
        assert received_dt.year == 2026
        assert received_dt.month == 3
        assert received_dt.day == 19
        assert received_dt.hour == 10
        assert received_dt.minute == 58

    def test_received_dt_supports_isoformat(self):
        """received_dt must expose .isoformat() so app.py vline code never raises."""
        raw = self._dutchie_csv("03/19/2026 10:58 AM")
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(raw, filename="test.csv")
        assert received_dt is not None
        iso = received_dt.isoformat()
        assert "2026" in iso

    def test_received_dt_supports_normalize(self):
        """received_dt must support .normalize() used in WoW vline code."""
        raw = self._dutchie_csv("03/19/2026 10:58 AM")
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(raw, filename="test.csv")
        assert received_dt is not None
        day = received_dt.normalize()
        assert day == pd.Timestamp("2026-03-19")

    def test_unparseable_date_returns_none(self):
        """An unparseable date in the preamble must return None, not raise."""
        raw = self._dutchie_csv("NOT-A-DATE")
        received_dt, _, _ = parse_manifest_csv_xlsx_bytes(raw, filename="test.csv")
        # May be None (preferred) or a Timestamp if pandas guesses it – never a str.
        assert received_dt is None or isinstance(received_dt, pd.Timestamp)


# ===========================================================================
# parse_sales_report_bytes – dtype guarantees with preamble
# ===========================================================================

class TestParseSalesReportDtypeGuarantees:
    """Ensure parse_sales_report_bytes always returns correct dtypes when the
    CSV has a metadata preamble (the format user uploads)."""

    @staticmethod
    def _preamble_sales_csv() -> bytes:
        lines = [
            "Export Date:,03/20/2026",
            "Report Type:,Sales Report",
            "",
            "Order ID,Order Time,Product Name,Category,Total Inventory Sold,Net Sales",
            "1001,2026-03-19 09:00,Blue Dream 3.5g,Flower,2,90.00",
            "1002,2026-03-19 10:30,Sour Diesel 1g,Flower,1,45.00",
            "1003,2026-03-12 09:00,Blue Dream 3.5g,Flower,1,42.00",
        ]
        return "\n".join(lines).encode("utf-8")

    def test_order_time_is_datetime_with_preamble(self):
        df = parse_sales_report_bytes(self._preamble_sales_csv(), "sales.csv")
        assert pd.api.types.is_datetime64_any_dtype(df["order_time"]), (
            "order_time must be datetime dtype even when CSV has a metadata preamble"
        )

    def test_net_sales_is_numeric_with_preamble(self):
        df = parse_sales_report_bytes(self._preamble_sales_csv(), "sales.csv")
        assert pd.api.types.is_float_dtype(df["net_sales"]), (
            "net_sales must be float dtype even when CSV has a metadata preamble"
        )

    def test_row_count_correct_with_preamble(self):
        df = parse_sales_report_bytes(self._preamble_sales_csv(), "sales.csv")
        assert len(df) == 3

    def test_build_wow_does_not_raise_with_preamble_sales(self):
        """End-to-end: parse → build_wow_time_series must not raise int+str error."""
        df = parse_sales_report_bytes(self._preamble_sales_csv(), "sales.csv")
        # Should not raise
        deliv_ts, prior_ts = build_wow_time_series(df, pd.Timestamp("2026-03-19"))
        assert not deliv_ts.empty

    def test_build_time_series_does_not_raise_with_preamble_sales(self):
        """End-to-end: parse → build_time_series must not raise int+str error."""
        df = parse_sales_report_bytes(self._preamble_sales_csv(), "sales.csv")
        ts = build_time_series(df, pd.Timestamp("2026-03-19"), window_days=14)
        assert not ts.empty

