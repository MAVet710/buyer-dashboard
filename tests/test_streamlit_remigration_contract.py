from __future__ import annotations

from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def assert_markers(path: str, *markers: str) -> None:
    text = unescape(source(path))
    missing = [marker for marker in markers if marker not in text]
    assert not missing, f"{path} is missing Streamlit parity markers: {missing}"


def test_purchasing_category_opens_full_buyer_command_center():
    app = source("frontend/src/App.tsx")
    shell = source("frontend/src/components/AppShell.tsx")
    assert 'page === "Buyer Operations" || page === "Purchasing"' in app
    assert '<BuyerCommandCenterPage onNavigate={setPage} />' in app
    assert 'page === "Replenishment Policies" ? <PurchasingPage />' in app
    assert '{ label: "Overview", page: "Buyer Operations" }' in shell
    assert '{ label: "Replenishment Policies", page: "Replenishment Policies" }' in shell


def test_retail_inventory_exposes_product_360_catalog_and_audits():
    assert_markers(
        "frontend/src/components/AppShell.tsx",
        '{ label: "Product 360", page: "Retail Product 360" }',
        '{ label: "Catalog Administration", page: "Retail Catalog Admin" }',
        'page: "Inventory Audits"',
        'page: "Slow Movers"',
        'page: "MA Flower Equivalency"',
    )
    assert_markers(
        "frontend/src/App.tsx",
        'page === "Retail Product 360" || page === "Retail Product Master"',
        'page === "Retail Catalog Admin"',
        '<FocusedInventoryAudits />',
    )


def test_production_inventory_keeps_products_and_audits_first_class():
    assert_markers(
        "frontend/src/components/AppShell.tsx",
        '{ label: "Materials", page: "Production Inventory" }',
        '{ label: "Products", page: "Production Product Master" }',
        '{ label: "Inventory Audits", page: "Inventory Audits" }',
    )
    assert_markers(
        "frontend/src/App.tsx",
        'page === "Production Product Master"',
        'page === "Inventory Audits"',
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


def test_package_360_is_not_lineage_only_and_keeps_cross_workspace_actions():
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
        'Audits',
        'Lineage',
        'Audit this SKU',
        'Add / update in PO',
        'Open traceability',
        'buyer-dash-audit-product-focus',
        'buyer-dash-po-inventory-selection',
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
    assert_markers(
        "frontend/index.html",
        'html5-qrcode/2.3.8/html5-qrcode.min.js',
        'StreamlitScannerBarcodeDetector',
        'window.BarcodeDetector',
        'reader.scanFile',
    )


def test_inventory_receiving_keeps_traceability_mapping_labs_atomic_post_and_labels():
    assert_markers(
        "frontend/src/components/ReceiveInventory.tsx",
        'Inbound Queue',
        'Receive Details',
        'Review',
        'Post Inventory',
        'Labels',
        'METRC',
        'Mapped Product',
        'Pull read-only METRC lab results',
        '/receipts/batch',
        'Print labels',
        'Manual receipt',
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
        'Doobie Ops Brief',
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
        'Velocity Adjustment',
        'Days in Sales Period',
        'Category DOS (at a glance)',
        'Forecast Table',
        'Product-Level Rows',
        'buyer-brief',
        'inventory-check',
    )


def test_home_keeps_operations_inbox_and_role_aware_task_launchers():
    assert_markers(
        "frontend/src/pages/HomePage.tsx",
        'Operations Home',
        'Needs attention · Operations Inbox',
        'Start a Task',
        'Start inventory audit',
        'Traceability queue',
        'Open Package Studio',
        'Build purchasing decisions',
        'Plan Co-Man production',
        'Review extraction',
        'Manage orders',
        'Import operational data',
    )


def test_orders_keeps_command_entry_execution_partners_audits_ledger_and_finance():
    assert_markers(
        "frontend/src/pages/OrdersPage.tsx",
        'Command Center',
        'New Order',
        'Allocate & Fulfill',
        'Trade Partners',
        'Inventory Audits',
        'Inventory Ledger',
        'Wholesale + Finance',
        'Incoming purchase orders',
        'Outgoing sales orders',
    )


def test_coman_production_keeps_full_planning_and_execution_surface():
    assert_markers(
        "frontend/src/pages/ProductionPage.tsx",
        'Dashboard',
        'New Job',
        'Schedule',
        'Resources',
        'Inventory & BOM',
        'Customers',
        'Performance',
        'machine_models',
        'reservations',
        'actuals',
        'attainment_pct',
    )


def test_white_label_repack_keeps_original_five_step_economics_workflow():
    assert_markers(
        "frontend/src/pages/WhiteLabelRepackPage.tsx",
        'Step 1: Bulk Lot',
        'Step 2: Costs',
        'Step 3: Package Plan',
        'Step 4: Results',
        'Step 5: Compliance',
        'Save Scenario',
        'Duplicate Scenario',
        'Export Retail Ops Report',
        'Gross Profit',
        'Gross Margin %',
        'Source METRC Package ID',
    )


def test_data_hub_keeps_readiness_import_mapping_history_and_production_intake():
    assert_markers(
        "frontend/src/pages/DataSettingsPage.tsx",
        'Readiness',
        'Import Retail Data',
        'Import Production Data',
        'History',
        'Ask Mapping Agent',
        'Publish source',
        'Archive active sources',
        'Raw Data Upload Staging',
    )


def test_admin_keeps_users_passwords_roles_orgs_facilities_and_license_context():
    assert_markers(
        "frontend/src/pages/AdminPage.tsx",
        'User Management',
        'Create User',
        'Manage Existing',
        'Temporary password',
        'Confirm temporary password',
        'Require password change',
        'Platform Organizations & Facilities',
        'Add Organization',
        'Add Facility',
        'facility_ids',
    )
    assert_markers(
        "frontend/src/pages/AdminToolsPage.tsx",
        'Facility license & operation context',
        'License number',
        'License type',
        'Retail',
        'Production / Manufacturing',
        'Cultivation',
        'Commercial',
        'Admin Uploads',
        'Operational diagnostics',
    )


def test_integrations_keep_facility_scoped_metrc_and_dev_doobie_controls():
    assert_markers(
        "frontend/src/pages/IntegrationsPage.tsx",
        'METRC User API Key',
        'METRC State',
        'METRC License / Facility',
        'Test Connection',
        'Clear / Reset',
        'Doobie Service API Key',
    )


def test_traceability_keeps_queue_reconciliation_attempts_lifecycle_and_payload_evidence():
    assert_markers(
        "frontend/src/pages/CompliancePage.tsx",
        'Queue & Reconciliation',
        'Needs reconciliation',
        'In flight',
        'Attempts',
        'Lifecycle',
        'Payloads',
        'Requeue',
        'Mark verified',
        'Cancel action',
    )


def test_classic_navigation_does_not_hide_major_workspaces():
    shell = source("frontend/src/components/AppShell.tsx")
    for category in ("Inventory", "Purchasing", "Orders", "Reports", "Compliance"):
        assert f'secondaryItems("{category}", operation, role)' in shell
    for category in ("Inventory", "Production", "Orders", "Compliance"):
        assert f'secondaryItems("{category}", operation, role)' in shell


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
