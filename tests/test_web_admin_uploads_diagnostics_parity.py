from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.database import get_engine
from backend.app.main import app
from tests.test_web_inventory_api import _engine


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_tools_restore_streamlit_upload_viewer_labels_and_safe_diagnostics():
    streamlit = read("app.py")
    web = read("frontend/src/pages/AdminToolsPage.tsx")
    backend = read("backend/app/routers/admin_uploads.py")
    main = read("backend/app/main.py")

    for label in (
        "Admin Uploads",
        "This panel displays sensitive user-uploaded data.",
        "Clear all stored uploads",
        "No uploads logged yet.",
        "Download an uploaded file",
        "Select upload",
        "Uploader:",
        "Role:",
    ):
        assert label in streamlit
        assert label in web
    assert "Doobie diagnostics, compliance source QA, and operational admin utilities." in streamlit
    assert "Doobie diagnostics, compliance source QA, and operational admin utilities." in web
    assert "_UPLOAD_TTL_MINUTES = 60" in backend
    assert 'entity_type="admin_upload_viewer"' in backend
    assert 'action="viewer_cleared"' in backend
    assert "payload_compressed" in backend
    assert "organization_id == context.organization_id" in backend
    assert "secret_hint" in backend
    assert "encrypted_secret" not in web
    assert "admin_uploads_router" in main


def test_admin_upload_viewer_lists_downloads_and_clears_without_destroying_source_data():
    engine = _engine()
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    headers = {
        "X-Organization-Id": "org-1",
        "X-Facility-Id": "facility-1",
        "X-User-Id": "admin@example.com",
        "X-User-Role": "admin",
    }
    payload = b"Product Name,Category,On Hand\nBlue Dream,Flower,42\n"
    try:
        uploaded = client.post(
            "/api/v1/data-hub/datasets",
            headers=headers,
            data={"dataset_key": "inventory"},
            files={"file": ("inventory.csv", payload, "text/csv")},
        )
        viewer = client.get("/api/v1/admin/uploads", headers=headers)
        upload_id = viewer.json()["uploads"][0]["upload_id"]
        downloaded = client.get(f"/api/v1/admin/uploads/{upload_id}/download", headers=headers)
        diagnostics = client.get("/api/v1/admin/diagnostics", headers=headers)
        cleared = client.post("/api/v1/admin/uploads/clear", headers=headers, json={})
        after_clear = client.get("/api/v1/admin/uploads", headers=headers)
        durable = client.get("/api/v1/data-hub/datasets", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert uploaded.status_code == 201
    assert viewer.status_code == 200
    assert viewer.json()["ttl_minutes"] == 60
    assert viewer.json()["uploads"][0]["filename"] == "inventory.csv"
    assert downloaded.status_code == 200 and downloaded.content == payload
    assert diagnostics.status_code == 200
    assert diagnostics.json()["durable_upload_versions"] == 1
    assert cleared.json() == {"cleared": True}
    assert after_clear.json()["uploads"] == []
    assert durable.json()["history"][0]["filename"] == "inventory.csv"
