from io import BytesIO

import pandas as pd
from PyPDF2 import PdfReader

from reports.buyer_report import _build_buyer_executive_report_pdf
from reports.coman_report import _build_coman_executive_report_pdf
from reports.competitor_report import _build_competitor_intelligence_report_pdf
from reports.executive_system import (
    ExecutiveReportSpec,
    ReportSection,
    RETAIL_PALETTE,
    build_executive_pdf,
    combine_report_pdfs,
)
from reports.extraction_report import _build_extraction_executive_report_pdf
from reports.retail_ops_report import _build_retail_ops_executive_report_pdf
from reports.white_label_report import _build_white_label_repack_report_pdf


def _reader(pdf: bytes) -> PdfReader:
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    assert reader.pages
    assert all(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages)
    assert all((page.extract_text() or "").strip() for page in reader.pages)
    return reader


def _all_text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_retail_report_family_uses_retail_branding_and_expected_sections():
    buyer = _build_buyer_executive_report_pdf(
        {
            "store_name": "Test Store",
            "detail_view": pd.DataFrame(
                [
                    {
                        "item": "Flower A",
                        "category": "Flower",
                        "onhand": 20,
                        "unitssold": 12,
                        "avgunitsperday": 2,
                        "daysonhand": 10,
                        "reorderqty": 8,
                    }
                ]
            ),
            "inv_df": pd.DataFrame([{"onhandunits": 20, "inventoryvalue": 400}]),
            "sales_df": pd.DataFrame([{"unitssold": 12}]),
        }
    )
    white_label = _build_white_label_repack_report_pdf(
        {
            "summary": {"strain_name": "Blue Dream"},
            "package_output_summary": pd.DataFrame(
                [
                    {
                        "Package Size": 3.5,
                        "Allocation %": 100,
                        "Grams Allocated": 350,
                        "Units": 100,
                        "Revenue": 3500,
                        "Gross Profit": 1400,
                        "Gross Margin %": 40,
                        "Status": "Ready",
                    }
                ]
            )
        }
    )
    retail_labor = _build_retail_ops_executive_report_pdf(
        {
            "metrics": {"total_labor_cost": 1000, "labor_health_status": "Balanced"},
            "analysis": pd.DataFrame([{"schedule_status": "Balanced", "total_sales": 5000}]),
            "demand": pd.DataFrame(
                [{"product_name": "Retail Flower A", "total_sales": 5000}]
            ),
        }
    )
    competitor = _build_competitor_intelligence_report_pdf(
        {
            "competitor_snapshot_df": pd.DataFrame(
                [
                    {
                        "competitor_name": "Market A",
                        "product_name": "Market Flower A",
                        "category": "Flower",
                        "effective_price": 35,
                        "discount_pct": 10,
                    }
                ]
            )
        }
    )
    for pdf, title in [
        (buyer, "Buyer Operations Executive Report"),
        (white_label, "White Label / Repack Executive Report"),
        (retail_labor, "Retail Labor Operations Executive Report"),
        (competitor, "Competitor Intelligence Executive Report"),
    ]:
        text = _all_text(_reader(pdf))
        assert "RETAIL OPS" in text
        assert title in text
        assert "CONFIDENTIAL - INTERNAL OPERATIONS" in text
        assert "â" not in text


    buyer_text = _all_text(_reader(buyer))
    white_label_text = _all_text(_reader(white_label))
    retail_labor_text = _all_text(_reader(retail_labor))
    competitor_text = _all_text(_reader(competitor))
    assert "product name" in buyer_text.lower() and "Flower A" in buyer_text
    assert "product name" in white_label_text.lower() and "Blue Dream" in white_label_text
    assert "product name" in retail_labor_text.lower() and "Retail Flower A" in retail_labor_text
    assert "product name" in competitor_text.lower() and "Market Flower A" in competitor_text


def test_production_report_family_uses_production_branding():
    extraction = _build_extraction_executive_report_pdf(
        {
            "kpis": {"total_runs": 1, "avg_yield_pct": 7.5},
            "run_performance": pd.DataFrame(
                [
                    {
                        "run id": "RUN-1",
                        "product name": "Live Resin A",
                        "method": "Hydrocarbon",
                        "input weight g": 1000,
                        "finished output g": 75,
                        "yield pct": 7.5,
                    }
                ]
            ),
        }
    )
    coman = _build_coman_executive_report_pdf(
        {
            "orders": pd.DataFrame(
                [
                    {
                        "Order": "WO-1",
                        "Type": "External",
                        "Product": "3.5 g Flower",
                        "Units": 1000,
                        "Status": "Scheduled",
                    }
                ]
            )
        }
    )
    for pdf, title in [
        (extraction, "Extraction Operations Executive Report"),
        (coman, "Co-Man Production Executive Report"),
    ]:
        text = _all_text(_reader(pdf))
        assert "PRODUCTION OPS" in text
        assert title in text
        assert "CONFIDENTIAL - INTERNAL OPERATIONS" in text
        assert "â" not in text


    extraction_text = _all_text(_reader(extraction))
    coman_text = _all_text(_reader(coman))
    assert "product name" in extraction_text.lower() and "Live Resin A" in extraction_text
    assert "product name" in coman_text.lower() and "3.5 g Flower" in coman_text


def test_combined_report_pack_preserves_all_reports():
    retail = _build_retail_ops_executive_report_pdf({})
    production = _build_coman_executive_report_pdf({})
    combined = combine_report_pdfs(
        [retail, production],
        title="DoobieLogic Company Executive Pack",
        division="All Operations",
    )
    reader = _reader(combined)
    text = _all_text(reader)
    assert "Retail Labor Operations Executive Report" in text
    assert "Co-Man Production Executive Report" in text


def test_buyer_report_uses_product_level_names_in_every_action_table():
    pdf = _build_buyer_executive_report_pdf(
        {
            "detail_view": pd.DataFrame(
                [
                    {
                        "subcategory": "Flower",
                        "onhandunits": 10,
                        "unitssold": 20,
                        "avgunitsperday": 2,
                        "daysonhand": 5,
                        "reorderqty": 50,
                    }
                ]
            ),
            "detail_product": pd.DataFrame(
                [
                    {
                        "product_name": "Blue Dream Flower 3.5g",
                        "subcategory": "Flower",
                        "onhandunits": 10,
                        "unitssold": 20,
                        "avgunitsperday": 2,
                        "daysonhand": 5,
                    }
                ]
            ),
            "doh_threshold": 30,
        }
    )

    text = _all_text(_reader(pdf))
    assert "Reorder Action List" in text
    assert "Inventory Exceptions" in text
    assert "Product Performance Detail" in text
    assert text.count("Blue Dream Flower 3.5g") >= 3


def test_long_report_tables_repeat_section_identity_on_every_continuation_page():
    rows = pd.DataFrame(
        [
            {
                "Product Name": f"Test Product {index:03d}",
                "SKU": f"SKU-{index:03d}",
                "On Hand": index + 1,
                "Days on Hand": 20 + index,
            }
            for index in range(120)
        ]
    )
    pdf = build_executive_pdf(
        ExecutiveReportSpec(
            title="Pagination Test",
            subtitle="Readable continuation pages",
            palette=RETAIL_PALETTE,
            sections=[
                ReportSection(
                    "Product Inventory Detail",
                    rows,
                    "Named rows must remain understandable after a page break.",
                    max_rows=120,
                )
            ],
        )
    )
    reader = _reader(pdf)
    table_pages = [
        page.extract_text() or ""
        for page in reader.pages
        if "Test Product" in (page.extract_text() or "")
    ]

    assert len(table_pages) >= 2
    assert all("Product Inventory Detail" in page for page in table_pages)
    assert all("PRODUCT NAME" in page for page in table_pages)
