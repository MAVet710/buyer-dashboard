import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import get_engine
from backend.app.main import app
from modules.data_hub_repository import DataHubRepository
from tests.test_web_inventory_api import _engine


ROOT = Path(__file__).resolve().parents[1]


def test_data_hub_review_mapping_publish_flow_is_durable_and_scoped():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {"X-Organization-Id": "org-1", "X-Facility-Id": "facility-1", "X-User-Id": "buyer@example.com", "X-User-Role": "buyer"}
    admin_headers = {**headers, "X-User-Role": "admin"}
    csv = b"Item Description,Dept,Qty Movement\nBlue Dream,Flower,10\n"
    mapping = {"Product": "Item Description", "Category": "Dept", "Units sold": "Qty Movement"}
    try:
        preview = client.post("/api/v1/data-hub/datasets/inspect", headers=headers, data={"dataset_key": "product_sales"}, files={"file": ("odd-sales.csv", csv, "text/csv")})
        suggestions = client.post("/api/v1/data-hub/datasets/mapping-suggestions", headers=headers, json={"dataset_key": "product_sales", "columns": preview.json()["source_columns"], "existing_matches": preview.json()["matches"]})
        duplicate = client.post("/api/v1/data-hub/datasets/publish", headers=headers, data={"dataset_key": "product_sales", "mapping_json": json.dumps({"Product": "Item Description", "Category": "Dept", "Units sold": "Dept"})}, files={"file": ("odd-sales.csv", csv, "text/csv")})
        published = client.post("/api/v1/data-hub/datasets/publish", headers=headers, data={"dataset_key": "product_sales", "mapping_json": json.dumps(mapping)}, files={"file": ("odd-sales.csv", csv, "text/csv")})
        listing = client.get("/api/v1/data-hub/datasets", headers=headers)
        isolated = client.get("/api/v1/data-hub/datasets", headers={**headers, "X-Facility-Id": "other-facility"})
        source = DataHubRepository(engine).list_active_sources("org-1", "facility-1")[0]
        buyer_archive = client.post("/api/v1/data-hub/archive", headers=headers, json={})
        archived = client.post("/api/v1/data-hub/archive", headers=admin_headers, json={})
        after_archive = client.get("/api/v1/data-hub/datasets", headers=admin_headers)
    finally:
        app.dependency_overrides.clear()
    assert preview.status_code == 200
    assert preview.json()["rows"] == 1
    assert preview.json()["preview"][0]["Item Description"] == "Blue Dream"
    assert preview.json()["requirements"] == ["Product", "Units sold", "Category"]
    assert suggestions.status_code == 200
    assert "row values were not sent" in suggestions.json()["privacy_note"]
    assert duplicate.status_code == 422
    assert published.status_code == 201
    assert published.json()["quality"] == "Ready"
    assert published.json()["mapping"] == mapping
    assert b"Product Name" in source.payload and b"Quantity Sold" in source.payload and b"Category" in source.payload
    assert len(listing.json()["status"]) == 10
    assert next(row for row in listing.json()["status"] if row["dataset"] == "Product Sales")["status"] == "Ready"
    assert next(row for row in listing.json()["status"] if row["dataset"] == "Co-Man Master Data")["status"] == "Ready"
    assert isolated.json()["history"] == []
    assert buyer_archive.status_code == 403
    assert archived.json()["archived"] == 1
    assert after_archive.json()["history"][0]["status"] == "archived"


def test_react_data_hub_preserves_streamlit_tabs_steps_controls_and_order():
    source = (ROOT / "frontend" / "src" / "pages" / "DataSettingsPage.tsx").read_text(encoding="utf-8")
    labels = [
        "Data Hub", "Load operational data once", "Sources Ready", "Retail Sources", "Extraction Runs", "Active Facility",
        "Readiness", "Import Retail Data", "Import Production Data", "History", "Operational source status",
        "Import retail data", "1. Choose the dataset", "2. Upload the source file", "3. Review detected structure",
        "Rows", "Columns", "Quality", "Ask Mapping Agent", "Mapping Agent suggestions", "Confirm column mapping",
        "Preview first 8 rows", "I reviewed the source and want it available to Retail Operations.",
        "4. ", "Publish source", "Replace current source", "Production Ops source intake", "Co-Man durable data",
        "Raw Data Upload Staging", "Upload extraction runs file", "Default values for missing mapped fields",
        "Auto-mapping confidence is low", "Mapped run preview", "Append mapped runs to Extraction Command Center",
        "Skipped ", "duplicate runs based on run_date + batch_id_internal + method", "Upload diagnostics",
        "Archive durable sources", "Archive active sources", "Historical revisions remain visible",
        "No sources have been published for this facility yet.",
    ]
    for label in labels:
        assert label in source
    assert '["Readiness","Import Retail Data","Import Production Data","History"]' in source
    assert "datasets/inspect" in source
    assert "datasets/mapping-suggestions" in source
    assert "datasets/publish" in source
    assert "partner-import/inspect" in source
    assert "partner-import/publish" in source
