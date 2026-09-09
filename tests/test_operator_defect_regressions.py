from pathlib import Path

import pandas as pd

from backend.app.routers.buyer_legacy_overview import _date_column


ROOT = Path(__file__).resolve().parents[1]


def test_camera_scanner_has_visible_ui_and_cross_browser_qr_fallback():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    scanner = (ROOT / "frontend" / "src" / "components" / "CameraScanner.tsx").read_text(encoding="utf-8")
    audits = (ROOT / "frontend" / "src" / "components" / "InventoryAudits.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "src" / "components" / "camera-scanner.css").read_text(encoding="utf-8")
    assert "html5-qrcode/2.3.8" in index
    assert "StreamlitScannerBarcodeDetector" in index
    assert 'formats: ["qr_code"]' in index
    assert "decodeWithFallback" in index
    assert "doobielogic-camera-frame.png" in index
    assert "Open camera scanner" in scanner
    assert "Camera ready — point it at a QR code or barcode" in scanner
    assert "camera-scan-frame" in scanner
    assert "RESCAN_GUARD_MS" in scanner
    assert "schedule(350)" in scanner
    assert 'import { CameraScanner } from "./CameraScanner"' in audits
    assert ".camera-scanner-card" in styles


def test_printed_inventory_labels_encode_external_package_id_as_qr():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    inventory = (ROOT / "frontend" / "src" / "pages" / "InventoryPage.tsx").read_text(encoding="utf-8")
    qr = (ROOT / "frontend" / "src" / "components" / "PackageQrCode.tsx").read_text(encoding="utf-8")
    assert "qrcode-generator/1.4.4" in index
    assert 'import { PackageQrCode } from "../components/PackageQrCode"' in inventory
    assert '<PackageQrCode value={row.package_id}/>' in inventory
    assert "inventory-label-qr" in qr
    assert "QR code for external package ID" in qr
    assert 'qr.addData(clean, "Byte")' in qr
    assert "row.package_id" in inventory


def test_purchasing_condition_kpis_drive_inventory_status_views():
    buyer = (ROOT / "frontend" / "src" / "pages" / "BuyerOperationsPage.tsx").read_text(encoding="utf-8")
    overview = (ROOT / "frontend" / "src" / "components" / "BuyerLegacyOverview.tsx").read_text(encoding="utf-8")
    assert "selectInventoryCondition" in buyer
    assert 'setSkuTab(target)' in buyer
    assert 'target === "no-stock"' in buyer
    assert 'id="buyer-status-views"' in buyer
    assert 'onClick={() => selectInventoryCondition("reorder")}' in buyer
    assert 'onClick={() => selectInventoryCondition("no-stock")}' in buyer
    assert 'onClick={() => selectInventoryCondition("overstock")}' in buyer
    assert 'onClick={() => selectInventoryCondition("expiring")}' in buyer
    assert "onInventoryCondition" in overview


def test_extraction_inventory_uses_eligible_projection_with_full_inventory_escape_hatch():
    source = (ROOT / "frontend" / "src" / "pages" / "ExtractionUnifiedPage.tsx").read_text(encoding="utf-8")
    assert "/api/v1/extraction-inventory/lots" in source
    assert "/api/v1/inventory/production/packages?view=all" not in source
    assert "fallbackLots" not in source
    assert "View all Production Inventory" in source
    assert "METRC / external package" in source


def test_buyer_overview_accepts_order_time_for_chart_data():
    frame = pd.DataFrame(columns=["product_name", "unitssold", "Order Time", "net_sales"])
    assert _date_column(frame) == "Order Time"


def test_buyer_overview_uses_elevated_live_data_charts():
    source = (ROOT / "frontend" / "src" / "components" / "BuyerLegacyOverview.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "src" / "buyer-streamlit.css").read_text(encoding="utf-8")
    assert "buyer-area-fill" in source
    assert "buyer-chart-kpis" in source
    assert "7-day movement" in source
    assert "Revenue by Category" in source
    assert "buyer-chart-elevated" in styles
    assert "buyer-category-rank" in styles


def test_workspace_restoration_self_heals_instead_of_dead_ending():
    gate = (ROOT / "frontend" / "src" / "components" / "PasswordGate.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "loadAccountContext" in gate
    assert "15000" in gate
    assert "syncStoredContextFromSession" in gate
    assert "Recover workspace" in gate
    assert "retry: false" in gate
    assert "response.status === 401" in api
    assert "refreshSession" in api
    assert "ApiError" in api


def test_api_surfaces_field_level_validation_errors():
    api = (ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "validationDetails" in api
    assert "const fieldErrors = validationDetails(payload.detail)" in api
    assert "if (fieldErrors) return fieldErrors"
    assert "One or more request fields are invalid" in api


def test_web_release_publishes_exact_render_commit_identity():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    static = blueprint.split("name: doobielogic-ops", 1)[1]
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "runtime: static" in static
    assert "autoDeployTrigger: checksPass" in static
    assert "RENDER_GIT_COMMIT" in static
    assert "release.json" in static
    assert "path: /release.json" in static
    assert "no-store, no-cache, must-revalidate" in static
    assert "doobielogic.io" in static
    assert "ops.doobielogic.io" in static
    assert "Verify Render handoff is exact-source and check-gated" in workflow
