from pathlib import Path
from io import BytesIO

import pandas as pd
import pytest

from backend.app.auth import RequestContext
from backend.app.routers import po_parity
from backend.app.routers.po_parity import POLine, POPdfRequest, POReviewRequest
from services.pdf_compat import PdfReader
from services.web_buyer_parity import records
from services.web_buying_budget_parity import build_budget, calculate_active_inventory_cost


ROOT = Path(__file__).resolve().parents[1]


def test_purchase_order_review_uses_streamlit_exact_name_size_and_15_unit_threshold(monkeypatch):
    xref = pd.DataFrame([
        {"product_name": "Blue Dream 3.5g", "packagesize": "3.5g", "onhandunits": 10},
        {"product_name": "Blue Dream 3.5g", "packagesize": "3.5g", "onhandunits": 5},
        {"product_name": "Blue Dream 3.5g", "packagesize": "7g", "onhandunits": 100},
    ])
    monkeypatch.setattr(po_parity, "_inventory_rows", lambda *_args, **_kwargs: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), xref))
    result = po_parity.review_lines(
        POReviewRequest(items=[
            POLine(description="Blue Dream 3.5g", size="3.5 g", quantity=1),
            POLine(description="Blue Dream 3.5g", size="7g", quantity=200),
            POLine(description="No Match", quantity=100),
        ]),
        21, 0.5, 60, 56,
        RequestContext("buyer", "org-1", "facility-1", "buyer"),
        object(),
    )
    assert result[0]["on_hand"] == 15 and result[0]["review"] is True and result[0]["review_reason"] == ">=15 on hand"
    assert result[1]["on_hand"] == 100 and result[1]["review"] is True
    assert result[2]["on_hand"] == 0 and result[2]["review"] is False and result[2]["review_reason"] == ""


def test_purchase_order_pdf_matches_streamlit_title_fields_totals_and_filename():
    payload = POPdfRequest(
        store_name="Cannabis Store", store_number="12", store_address="123 Main St", store_phone="555-0100", store_contact="Buyer One",
        vendor_name="Vendor One", vendor_license="LIC-1", vendor_address="456 Vendor Rd", vendor_contact="Seller One",
        po_number="PO-20260822", po_date="2026-08-22", terms="Net 30",
        fulfillment_notes="Buyer email: buyer@example.com\nRequested delivery: 08/29/2026\nShipping method: Vendor delivery",
        tax_rate=10, discount=5, shipping=2, items=[POLine(sku="SKU-1", description="Blue Dream", strain="Blue Dream", size="3.5g", quantity=2, price=10)],
    )
    body = po_parity._pdf(payload)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(body)).pages)
    response = po_parity.generate_pdf(payload)
    assert "MAVet710 - Purchase Order" in text
    assert "PO Number: PO-20260822" in text and "Date: 08/22/2026" in text
    assert "Store #: 12" in text and "License #: LIC-1" in text and "Payment Terms:" in text
    assert "Subtotal: $20.00" in text and "Discount: -$5.00" in text and "Tax: $2.00" in text and "Shipping / Fees: $2.00" in text and "TOTAL: $19.00" in text
    assert 'filename="PO_PO-20260822_' in response.headers["content-disposition"]


def test_buying_budget_formulas_columns_scenarios_and_total_cost_precedence_match_streamlit():
    sales = pd.DataFrame({"Date":["2026-08-01","2026-08-30"],"Net Sales":[100,200],"Category":["Flower","Flower"]})
    inventory = pd.DataFrame({"Product Name":["Blue Dream"],"Category":["Flower"],"Quantity":[10],"Total Cost":[100],"Unit Cost":[999]})
    result = build_budget(inventory, sales)
    summary = result["summary"]
    category = result["categories"][0]
    scenarios = {row["Scenario"]: row for row in result["scenarios"]}
    assert summary["sales_window_total"] == 300
    assert summary["avg_daily_cogs"] == 5
    assert summary["active_inventory_cost"] == 100
    assert summary["target_inventory_cost"] == pytest.approx(247.5)
    assert summary["recommended_budget"] == pytest.approx(147.5)
    assert category["Category"] == "Flower" and category["Sales Window Retail Sales"] == 300 and category["Avg Daily Sales"] == 10 and category["Avg Daily COGS"] == 5
    assert category["Current Inventory at Cost"] == 100 and category["Target Inventory at Cost"] == pytest.approx(247.5) and category["Recommended Budget"] == pytest.approx(147.5)
    assert category["Budget Status"] == "Buy" and category["Notes"] == "Allocate purchasing budget"
    assert scenarios["Conservative"]["Recommended Budget"] == pytest.approx(57.5)
    assert scenarios["Balanced"]["Recommended Budget"] == pytest.approx(147.5)
    assert scenarios["Aggressive"]["Recommended Budget"] == pytest.approx(279.5)
    _frame, total = calculate_active_inventory_cost(inventory, 0.5, False, False, False)
    assert total == 100


def test_react_purchase_order_and_budget_preserve_streamlit_labels_defaults_and_source_order():
    po_source = (ROOT / "frontend" / "src" / "pages" / "PurchaseOrdersParityPage.tsx").read_text(encoding="utf-8")
    budget_source = (ROOT / "frontend" / "src" / "pages" / "BuyingBudgetPage.tsx").read_text(encoding="utf-8")
    ordered_po = ["Purchase Order Builder", "📊 Reorder Cross-Reference (from Inventory Dashboard)", "📋 Order Information", "📦 Line Items", "Current Items", "💰 Totals", "Smart PO (additive)"]
    assert [po_source.index(label) for label in ordered_po] == sorted(po_source.index(label) for label in ordered_po)
    for label in [
        "Store Name","Store Address","Vendor Name","Vendor Address","PO Number","PO Date","Buyer / Contact Name","Buyer Phone","Buyer Email","Store / Location Number",
        "Vendor Contact","Vendor License Number","Requested Delivery Date","Shipping Method","Payment Terms","Delivery Instructions","PO Notes",
        "SKU","Description","Strain","Size","Qty","Price","Tax Rate (%)","Discount ($)","Shipping ($)","🗑️ Clear All Items","📄 Generate PDF","📥 Download PDF",
    ]:
        assert label in po_source
    assert "Target Days on Hand" not in po_source
    assert "table-input" not in po_source
    for label in ["Purchasing Budget","Planning sales window","Target DOS","COGS % fallback","Safety stock %","Growth adjustment %","Include dead stock?","Include quarantine inventory?","Include accessories?","On-order inventory cost","Recommended Purchasing Budget","Current Active Inventory at Cost","Target Inventory at Cost","Over/Under Position","Avg Daily COGS","On Order Cost","Category-Level Recommended Budget","Recommended Budget by Category","Current vs Target Inventory by Category","Budget Scenario Table","Remaining Budget After PO"]:
        assert label in budget_source
    assert "const [days,setDays] = useState(30)" in budget_source
    assert "const [target,setTarget] = useState(45)" in budget_source
    assert "const [cogs,setCogs] = useState(50)" in budget_source
    assert "const [safety,setSafety] = useState(10)" in budget_source


def test_purchasing_workspace_records_are_json_safe_when_optional_numeric_values_are_missing():
    payload = records(pd.DataFrame({"product_name": ["Blue Dream"], "days_of_supply": [float("nan")]}))
    assert payload == [{"product_name": "Blue Dream", "days_of_supply": None}]
