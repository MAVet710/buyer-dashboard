import pandas as pd
from io import BytesIO

from views.retail_ops_command_center import _normalize_data, _build_retail_ops_executive_report_pdf, _read_sales_upload


def test_normalize_data_computes_analysis():
    employees = pd.DataFrame([
        {"employee_name": "A", "hourly_wage": 20},
    ])
    schedule = pd.DataFrame([
        {"date": "2026-05-01", "employee_name": "A", "scheduled_hours": 8},
    ])
    sales = pd.DataFrame([
        {"date": "2026-05-01", "total_sales": 2000, "transactions": 80},
    ])
    thresholds = {
        "target_labor_pct_low": 12, "target_labor_pct_high": 18,
        "target_sales_per_labor_hour": 250, "target_transactions_per_labor_hour": 8,
        "minimum_staffing_floor": 1, "maximum_staffing_cap": 60,
    }
    _s, _d, analysis, data_quality = _normalize_data(
        employees, schedule, sales, thresholds
    )
    assert not analysis.empty
    assert "schedule_status" in analysis.columns
    assert data_quality["analysis_granularity"] == "daily"


def test_pdf_builder_returns_bytes():
    pdf = _build_retail_ops_executive_report_pdf({"summary_lines": ["x"], "recommendations": ["y"]})
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 100


def test_read_sales_upload_detects_pos_hour_totals_and_normalizes():
    raw = pd.DataFrame([
        ["Export Date", "2026-05-12"],
        ["From Date", "2026-05-01"],
        ["To Date", "2026-05-07"],
        ["Location", "Main St"],
        ["Location Name", "Day", "Starting Hour", "Total Orders", "Gross Sales", "Total Inventory Sold", "Total Delivery Orders"],
        ["Main St", "Monday", 11, 10, 1000, 20, 2],
        ["Main St", "Monday", 11, 5, 500, 10, 1],
    ])
    bio = BytesIO()
    raw.to_excel(bio, index=False, header=False)
    bio.seek(0)
    bio.name = "pos_hour_totals.xlsx"
    sales, metadata = _read_sales_upload(bio)
    assert metadata["source_type"] == "pos_hour_totals"
    assert metadata["detected_header_row"] == 5
    assert metadata["location"] == "Main St"
    assert len(sales) == 1
    assert float(sales.iloc[0]["transactions"]) == 15
    assert float(sales.iloc[0]["gross_sales"]) == 1500
    assert sales.iloc[0]["analysis_granularity"] == "weekday_hour"
