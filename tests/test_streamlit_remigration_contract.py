from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def assert_markers(path: str, *markers: str) -> None:
    text = source(path)
    missing = [marker for marker in markers if marker not in text]
    assert not missing, f"{path} is missing Streamlit parity markers: {missing}"


def test_purchasing_category_opens_full_buyer_command_center():
    app = source("frontend/src/App.tsx")
    assert 'page === "Buyer Operations" || page === "Purchasing"' in app
    assert '<BuyerCommandCenterPage onNavigate={setPage} />' in app
    assert 'page === "Replenishment Policies" ? <PurchasingPage />' in app


def test_retail_inventory_exposes_product_360_and_audits():
    assert_markers(
        "frontend/src/components/AppShell.tsx",
        'page: "Inventory Audits"',
        'page: "Retail Product Master"',
        'page: "Slow Movers"',
        'page: "MA Flower Equivalency"',
    )
    assert_markers(
        "frontend/src/App.tsx",
        'page === "Retail Product 360" || page === "Retail Product Master"',
        '<FocusedInventoryAudits />',
    )


def test_product_360_retains_all_streamlit_evidence_tabs_and_actions():
    assert_markers(
        "frontend/src/components/Product360Drawer.tsx",
        '"Overview"',
        '"Inventory"',
        '"Sales"',
        '"Purchasing"',
        '"Packages"',
        '"Compliance"',
        '"Audits"',
        'Audit this SKU',
        'Purchase Orders',
        'Open traceability',
        'buyer-dash-audit-product-focus',
        'buyer-dash-po-inventory-selection',
    )


def test_package_360_is_not_lineage_only():
    assert_markers(
        "frontend/src/components/PackageLineage.tsx",
        'Product360Workspace',
        '/product-360/by-lot/',
        '/lineage',
        'initialTab="packages"',
    )
    assert_markers(
        "frontend/src/components/Product360Workspace.tsx",
        'Inventory',
        'Sales',
        'Purchasing',
        'Packages',
        'Compliance',
        'Lineage',
    )


def test_scan_audit_keeps_phone_camera_and_resumable_lifecycle():
    assert_markers(
        "frontend/src/components/InventoryAudits.tsx",
        'navigator.mediaDevices.getUserMedia',
        'facingMode:{ideal:"environment"}',
        'BarcodeDetector',
        'Camera, Bluetooth/USB scanner, typed code, and manual product selection all remain available.',
        'Back to Dashboard',
        'Pause Audit',
        'Stop & Review',
        'Generate Current Report',
        'Export CSV',
        'Export Excel',
        'Start New Audit',
        'Resume',
        'stopped',
        'paused',
        'completed',
        'cancelled',
    )


def test_extraction_exposes_command_center_run_360_and_inventory():
    assert_markers(
        "frontend/src/pages/ExtractionUnifiedPage.tsx",
        'Command Center',
        'Run 360 / Process Tracker',
        'Extraction Inventory',
        '<ExtractionCommandCenterPage',
        '<ExtractionPage',
    )
    assert_markers(
        "frontend/src/pages/ExtractionCommandCenterPage.tsx",
        'Executive Overview',
        'Run Analytics',
        'Toll Processing',
        'Compliance',
        'METRC',
        'Data Input',
    )


def test_legacy_buyer_family_remains_first_class():
    assert_markers(
        "frontend/src/components/AppShell.tsx",
        'Buyer Operations',
        'Buying Recommendations',
        'Delivery Performance',
        'Purchase Orders',
        'Buying Budget',
        'Replenishment Policies',
    )
    assert_markers(
        "frontend/src/pages/BuyerOperationsPage.tsx",
        'Target Days on Hand',
        'velocity',
        'forecast',
    )


def test_streamlit_admin_data_compliance_and_reports_destinations_are_reachable():
    app = source("frontend/src/App.tsx")
    for page in (
        "Data & Settings",
        "Location Settings",
        "Admin",
        "Integrations",
        "Compliance",
        "Compliance Q&A",
        "Product Name Mapper",
        "Executive Reports",
        "Orders",
        "Production",
        "White Label / Repack",
    ):
        assert page in app
