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
