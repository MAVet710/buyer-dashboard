import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import get_engine
from backend.app.main import app
from modules.data_hub_repository import DataHubRepository
from tests.test_web_inventory_api import _engine


ROOT = Path(__file__).resolve().parents[1]
HEADERS = {
    "X-Organization-Id": "org-1",
    "X-Facility-Id": "facility-1",
    "X-User-Id": "buyer@example.com",
    "X-User-Role": "buyer",
}
SALES = b"""Order ID,Order Time,Product Name,Category,Total Inventory Sold,Net Sales
1,2026-03-01 10:00,Blue Dream 3.5g,Flower,1,30
2,2026-03-08 11:00,Blue Dream 3.5g,Flower,2,60
3,2026-03-15 12:00,Blue Dream 3.5g,Flower,3,90
4,2026-03-16 13:00,Blue Dream 3.5g,Flower,2,60
5,2026-03-17 14:00,Gummy 10pk,Edibles,1,25
6,2026-03-22 15:00,Blue Dream 3.5g,Flower,4,120
"""
MANIFEST_ONE = b"""Received Date,2026-03-15 09:00
Product Name,Received Qty
Blue Dream 3.5g,12
Unknown Product,4
"""
MANIFEST_TWO = b"""Received Date,2026-03-16 09:00,
Product Name,Received Qty,Package ID
Gummy 10pk,8,PKG-2
"""


def _publish_sales(engine, *, facility_id="facility-1"):
    return DataHubRepository(engine).publish_source(
        organization_id="org-1",
        facility_id=facility_id,
        dataset_key="product_sales",
        dataset_label="Product Sales",
        cache_key="sales_raw_df",
        filename="sales.csv",
        fingerprint=hashlib.sha256(SALES).hexdigest(),
        payload=SALES,
        inspection={"rows": 6, "columns": 6, "quality": "Ready"},
        content_type="text/csv",
        imported_by="buyer@example.com",
    )


def test_delivery_workspace_reuses_facility_sales_and_handles_multiple_manifests():
    engine = _engine()
    _publish_sales(engine)
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/buyer-parity/delivery-impact-workspace",
            headers=HEADERS,
            data={"use_active_sales": "true", "window_days": "14", "fuzzy_threshold": "0.82"},
            files=[
                ("manifests", ("manifest-one.csv", MANIFEST_ONE, "text/csv")),
                ("manifests", ("manifest-two.csv", MANIFEST_TWO, "text/csv")),
                ("manifests", ("invalid.csv", b"Product,Qty\nNo Date,1\n", "text/csv")),
            ],
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sales_source"] == "Buyer Dashboard sales data"
    assert payload["sales_rows"] == 6
    assert payload["sales_days"] == 6
    assert payload["sales_products"] == 2
    assert [row["filename"] for row in payload["manifests"]] == ["manifest-one.csv", "manifest-two.csv"]
    assert payload["invalid_manifests"][0]["filename"] == "invalid.csv"
    assert payload["invalid_manifests"][0]["reason"] == "No detectable received date/time."
    assert "Product,Qty" in payload["invalid_manifests"][0]["debug_text"]
    first = payload["manifests"][0]
    assert first["matched"]["Blue Dream 3.5g"] == "Blue Dream 3.5g"
    assert first["unmatched"] == ["Unknown Product"]
    assert first["kpis"]["net_sales_after"] == 295.0
    assert first["weekday_wow"]["net_sales_after"] == 90.0
    assert first["daily_series"] and first["hourly_series"]
    assert first["wow_daily_series"] and first["wow_prior_daily_series"]
    assert first["combined_kpis"] and first["combined_hourly_series"]


def test_delivery_workspace_accepts_uploaded_sales_and_enforces_scope():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    try:
        uploaded = client.post(
            "/api/v1/buyer-parity/delivery-impact-workspace",
            headers=HEADERS,
            data={"use_active_sales": "false", "window_days": "7", "fuzzy_threshold": "0.9"},
            files=[
                ("manifests", ("manifest.csv", MANIFEST_ONE, "text/csv")),
                ("sales", ("uploaded-sales.csv", SALES, "text/csv")),
            ],
        )
        missing = client.post(
            "/api/v1/buyer-parity/delivery-impact-workspace",
            headers={**HEADERS, "X-Facility-Id": "other-facility"},
            data={"use_active_sales": "true"},
            files=[("manifests", ("manifest.csv", MANIFEST_ONE, "text/csv"))],
        )
    finally:
        app.dependency_overrides.clear()
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["sales_source"] == "uploaded-sales.csv"
    assert uploaded.json()["window_days"] == 7
    assert uploaded.json()["fuzzy_threshold"] == 0.9
    assert missing.status_code in {403, 422}


def test_delivery_page_preserves_streamlit_controls_and_auto_analysis():
    source = (ROOT / "frontend" / "src" / "pages" / "DeliveryImpactPage.tsx").read_text(encoding="utf-8")
    for text in (
        "🚚 Delivery Impact Analysis",
        "Use sales data already loaded in Buyer Dashboard",
        "📅 Before/After (±N days)",
        "📆 Same weekday last week (WoW)",
        "Comparison window (days before/after)",
        "Chart granularity",
        "Fuzzy match threshold",
        "Delivered-items Net Sales",
        "Non-delivered Net Sales",
        "Order Count (traffic)",
        "📦 Combined (all manifests)",
        "🏆 Top Delivered Items by Lift",
        "🔍 View item matching results",
        "🐛 PDF debug text:",
    ):
        assert text in source
    assert "useEffect(()=>{void analyze()}" in source
    assert ">Analyze<" not in source
