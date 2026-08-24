from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_camera_scanner_has_native_and_cross_browser_qr_fallback():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "html5-qrcode/2.3.8" in index
    assert "StreamlitScannerBarcodeDetector" in index
    assert 'formats: ["qr_code"]' in index
    assert "decodeWithFallback" in index
    assert "doobielogic-camera-frame.png" in index


def test_printed_inventory_labels_encode_external_package_id_as_qr():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    inventory = (ROOT / "frontend" / "src" / "pages" / "InventoryPage.tsx").read_text(encoding="utf-8")
    assert "qrcode-generator/1.4.4" in index
    assert "inventory-label-qr" in index
    assert "QR code for external package ID" in index
    assert "qr.addData(packageId" in index
    assert "row.package_id" in inventory


def test_purchasing_condition_kpis_drive_inventory_status_views():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    buyer = (ROOT / "frontend" / "src" / "pages" / "BuyerOperationsPage.tsx").read_text(encoding="utf-8")
    assert ".buyer-filter-condition .metric, .buyer-condition-metrics .metric" in index
    assert "openBuyerStatusView" in index
    assert '"no-stock"' in index
    assert "buyer-status-views" in buyer
    assert "setSkuTab" in buyer


def test_extraction_inventory_falls_back_to_production_inventory():
    source = (ROOT / "frontend" / "src" / "pages" / "ExtractionUnifiedPage.tsx").read_text(encoding="utf-8")
    assert "/api/v1/extraction/lots" in source
    assert "/api/v1/inventory/production/packages?view=all" in source
    assert "fallbackLots" in source
    assert "METRC / external package" in source


def test_web_deploy_explicitly_promotes_new_revision():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    web_section = workflow.split("  deploy-web:", 1)[1]
    assert "Deploy frontend candidate without traffic" in web_section
    assert "--no-traffic" in web_section
    assert "Verify frontend candidate and promote to 100 percent" in web_section
    assert '--to-revisions "$CREATED_REVISION=100"' in web_section
    assert "https://ops.doobielogic.io" in web_section
    assert "https://doobielogic.io" in web_section
    assert "ops.doobielogic.io and doobielogic.io are serving the promoted web revision" in web_section
