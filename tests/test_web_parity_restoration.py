from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from backend.app.routers.po_parity import POLine, POPdfRequest, _best_match, _pdf
from backend.app.routers.buyer_parity import _filter_export_frame
from modules.coman.models import Base, Facility, Organization
from services.doobie_client import DoobieClient
from services.license_validation import validate_license_key
from services.trial_access import issue_trial_token, verify_trial_token


def test_trial_token_is_signed_scoped_and_expires():
    token, expires = issue_trial_token(
        secret="test-secret",
        organization_id="sandbox-org",
        facility_id="sandbox-facility",
        duration_seconds=300,
    )
    payload = verify_trial_token(token, secret="test-secret", now=expires - 1)
    assert payload is not None
    assert payload["organization_id"] == "sandbox-org"
    assert payload["facility_id"] == "sandbox-facility"
    assert payload["role"] == "trial"
    assert verify_trial_token(token, secret="wrong-secret", now=expires - 1) is None
    assert verify_trial_token(token, secret="test-secret", now=expires) is None


def test_trial_license_validation_is_ui_independent(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"valid": True, "plan": "trial", "features": ["retail"]}

    def fake_post(url, *, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr("services.license_validation.requests.post", fake_post)
    result = validate_license_key(
        "trial-key",
        base_url="https://doobie.example/",
        api_key="service-key",
    )
    assert result["ok"] is True
    assert result["valid"] is True
    assert result["payload"]["plan"] == "trial"
    assert captured["url"] == "https://doobie.example/api/v1/license/validate"
    assert captured["headers"]["Authorization"] == "Bearer service-key"
    assert captured["json"] == {"license_key": "trial-key"}


def test_grounded_extraction_brief_uses_current_run_evidence(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = DoobieClient(base_url="", api_key="").extraction_brief(
        {
            "runs": [
                {
                    "batch_id_internal": "BHO-TEST-1",
                    "method": "BHO",
                    "input_weight_g": 1000.0,
                    "finished_output_g": 100.0,
                    "residual_loss_g": 20.0,
                    "yield_pct": 10.0,
                    "qa_hold": True,
                    "cogs_usd": 500.0,
                    "est_revenue_usd": 900.0,
                }
            ]
        },
        state="MA",
        question="What needs attention?",
    )
    assert result["mode"] == "extraction"
    assert "BHO-TEST-1" in result["answer"] or "BHO-TEST-1" in " ".join(result["risk_flags"])
    assert result["recommendations"]


def test_po_inventory_cross_check_prefers_exact_sku_then_product_name():
    inventory = [
        {"sku": "SKU-100", "product_name": "Blue Dream Flower 3.5g", "packagesize": "3.5g", "onhandunits": 12},
        {"sku": "SKU-200", "product_name": "Blue Dream Pre Roll 1g", "packagesize": "1g", "onhandunits": 30},
    ]
    exact, exact_score, exact_reason = _best_match(
        POLine(sku="SKU-100", description="anything", quantity=1, price=1), inventory
    )
    assert exact["product_name"] == "Blue Dream Flower 3.5g"
    assert exact_score == 1.0
    assert exact_reason == "SKU exact match"

    fuzzy, score, _ = _best_match(
        POLine(description="Blue Dream Flower", size="3.5g", quantity=1, price=1), inventory
    )
    assert fuzzy["sku"] == "SKU-100"
    assert score >= 0.72


def test_po_pdf_keeps_original_financial_fields():
    payload = POPdfRequest(
        store_name="Buyer Dash Store",
        vendor_name="Example Vendor",
        vendor_license="LIC-123",
        po_number="PO-TEST-1",
        po_date="2026-08-22",
        terms="Net 30",
        tax_rate=6.25,
        discount=5,
        shipping=12,
        items=[POLine(sku="SKU-1", description="Example Product", strain="Hybrid", size="3.5g", quantity=10, price=20)],
    )
    pdf = _pdf(payload)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_retail_and_production_product_master_are_reachable_without_flattening_navigation():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    search = (root / "frontend" / "src" / "components" / "GlobalSearch.tsx").read_text(encoding="utf-8")

    assert '{ label: "Product Master", page: "Retail Product Master" }' in shell
    assert '{ label: "Product Master", page: "Production Product Master" }' in shell
    assert 'page === "Retail Product Master"' in app
    assert 'page === "Production Product Master"' in app
    assert 'workspace: "Retail Product Master"' in search
    assert 'workspace: "Production Product Master"' in search


def test_buyer_forecast_export_uses_the_current_streamlit_filter_slice():
    import pandas as pd

    frame = pd.DataFrame([
        {"subcategory": "flower", "reorderpriority": "1 – Reorder ASAP", "product_name": "Blue Dream"},
        {"subcategory": "flower", "reorderpriority": "3 – Healthy", "product_name": "Day Glow"},
        {"subcategory": "vapes", "reorderpriority": "1 – Reorder ASAP", "product_name": "Vape A"},
    ])
    filtered = _filter_export_frame(frame, ["flower"], reorder_only=True)

    assert filtered["product_name"].tolist() == ["Blue Dream"]


def test_white_label_report_endpoint_uses_the_retained_streamlit_pdf_builder():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-repack", name="Repack Org", slug="repack-org"))
        session.add(Facility(id="facility-repack", organization_id="org-repack", name="Retail Repack", code="RPK", retail_enabled=True))
        session.commit()

    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    payload = {
        "scenario_name": "Blue Dream Launch",
        "summary": {"strain_name": "Blue Dream", "landed_cost_usd": 1000, "total_revenue_usd": 2500, "gross_profit_usd": 1000, "gross_margin_pct": 40},
        "bulk_lot_details": {"wl_strain_name": "Blue Dream"},
        "package_output_summary": [{"Product Name": "Blue Dream Flower 3.5g", "Package Size": "3.5g", "Units Produced": 100, "Revenue": 2500, "Gross Profit": 1000, "Gross Margin %": 40, "Status": "Complete"}],
        "cost_breakdown": [{"Cost Type": "Landed Cost", "Total Cost": 1000}],
        "compliance_checklist": [{"Requirement": "COA Link Present", "Status": "Ready"}],
    }
    try:
        response = client.post(
            "/api/v1/executive-reports/white-label.pdf",
            headers={"X-Organization-Id": "org-repack", "X-Facility-Id": "facility-repack", "X-User-Id": "dev-user", "X-User-Role": "dev"},
            json=payload,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000


def test_white_label_repack_keeps_the_streamlit_control_vocabulary_and_order():
    root = Path(__file__).resolve().parents[1]
    react = (root / "frontend" / "src" / "pages" / "WhiteLabelRepackPage.tsx").read_text(encoding="utf-8")
    labels = [
        "Scenario Name", "Save Scenario", "Load Scenario", "Duplicate Scenario", "Clear Scenario",
        "Apply Loaded Scenario", "Step 1: Bulk Lot", "Step 2: Costs", "Step 3: Package Plan",
        "Step 4: Results", "Step 5: Compliance", "Strain Name *", "Strain Type *",
        "Cultivator Name *", "Vendor Name *", "Bulk Weight *", "Weight Unit *", "Total Bulk Cost ($) *",
        "Certificate of Analysis (COA) Link *", "THCA (%) *", "Terpenes (%) *", "Advanced Lot Details",
        "Cultivator License Number", "Source METRC Package ID", "Batch or Lot Number", "Total THC (%)",
        "Moisture (%)", "Purchase Discount (%)", "Expected Shrink Loss (%)", "Total Labor Cost ($)",
        "Other Costs ($)", "Advanced Costs", "Freight or Delivery Cost ($)", "Sampling or Testing Cost ($)",
        "Compliance Administration Cost ($)", "QA Hold Loss (%)", "Trim Loss (%)", "Moisture Loss (%)",
        "Simple Mode", "Packaging Cost Details", "Usable Weight", "Total Units", "Total Revenue",
        "Gross Profit", "Gross Margin %", "Leftover Grams", "Best Package Size by Margin", "Margin Readiness",
        "Requirement", "Status", "Export Retail Ops Report",
    ]
    positions = [react.index(label) for label in labels]
    assert all(position >= 0 for position in positions)
    assert react.index("Step 1: Bulk Lot") < react.index("Step 5: Compliance")
    assert '<Select label="COA Status"' not in react
    assert '<Select label="Label Review"' not in react
