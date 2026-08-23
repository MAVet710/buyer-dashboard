from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def has(path: str, *markers: str) -> None:
    body = text(path)
    missing = [marker for marker in markers if marker not in body]
    assert not missing, f"{path} missing remigration contract markers: {missing}"


def test_global_shell_preserves_streamlit_navigation_context_theme_and_mobile_behavior():
    has(
        "frontend/src/components/AppShell.tsx",
        '"Home"', '"Inventory"', '"Purchasing"', '"Orders"', '"Production"',
        '"Reports"', '"Compliance"', '"Data & Settings"',
        'BuyerDataMode = "Uploads" | "Dutchie Live"',
        'buyer-dash-data-mode', 'buyer-dash-classic-navigation',
        'aria-label="Organization"', 'aria-label="Facility"', 'aria-label="Operation"',
        '<GlobalSearch onNavigate={navigate}/>', '<MobileNavigation', '<ClassicNavigation',
        'capabilities.production || context.data.capabilities.cultivation',
    )
    has(
        "frontend/src/streamlit-exact.css",
        '--dl-copper:#E7984E', '--dl-copper-bright:#F4B36F', '--dl-radius-md:14px',
        'backdrop-filter:blur(16px)', 'box-shadow:0 18px 50px',
        'Streamlit dialogs are right-side drawers',
    )
    has(
        "frontend/src/streamlit-shell.css",
        '.mobile-flat-navigation', '.theme-toggle', '.context-switchers',
    )
    has(
        "frontend/src/main.tsx",
        '"./streamlit-exact.css"', '"./streamlit-shell.css"', '"./home-streamlit.css"',
        '"./inventory-receiving.css"',
    )


def test_home_matches_role_aware_streamlit_task_and_inbox_contract():
    has(
        "frontend/src/pages/HomePage.tsx",
        'Operations Home', 'Needs attention · Operations Inbox', 'Start a Task',
        'Review inventory', 'Start inventory audit', 'Traceability queue',
        'Open Package Studio', 'Build purchasing decisions', 'Plan Co-Man production',
        'Review extraction', 'Manage orders', 'Import operational data',
        'Product360Drawer', '/api/v1/home/inbox', '/api/v1/home/summary',
    )


def test_inventory_cross_workspace_actions_receiving_and_history_are_preserved():
    has(
        "frontend/src/pages/InventoryPage.tsx",
        'Product 360', 'Audit', 'Add to PO', 'Work on package', 'Print labels',
        'Adjust', 'Export selected', 'Package 360',
        'buyer-dash-po-inventory-selection', 'buyer-dash-audit-product-focus',
        '<ProductionReceiveInventory', '<ReceiveInventory operation="retail"', '<ReceiveHistory',
    )
    has(
        "frontend/src/components/ReceiveInventory.tsx",
        'Inbound Queue', 'Receive Details', 'Review', 'Post Inventory', 'Labels',
        'Mapped Product', 'Pull read-only METRC lab results', '/receipts/batch', 'Print labels',
    )
    has(
        "frontend/src/components/ProductionReceiveInventory.tsx",
        'PRODUCTION / CULTIVATION RECEIVING', 'Receive material', 'METRC package ID',
        'Internal lot / batch', 'Room / location', 'Source facility / supplier', 'Manifest / transfer #',
    )
    has(
        "frontend/src/components/ReceiveHistory.tsx",
        'Received', 'Product', 'Package', 'Quantity', 'Source', 'Manifest', 'Actor',
    )
    has(
        "frontend/src/components/Product360Drawer.tsx",
        'Overview', 'Inventory', 'Sales', 'Purchasing', 'Packages', 'Compliance', 'Audits',
        'Audit this SKU', 'Add / update in PO', 'Open traceability',
    )


def test_compliance_qa_and_nomenclature_mapper_keep_streamlit_operator_workflows():
    has(
        "frontend/src/pages/ComplianceQAPage.tsx",
        'Compliance Q&A', 'Download compliance source template', 'Required source columns',
        'state', 'scope', 'topic', 'answer', 'source_citation', 'source_url', 'last_updated', 'review_status',
        'Upload structured compliance sources', 'Answer from structured sources',
        'METRC State', 'Adult Use', 'Medical',
    )
    has(
        "frontend/src/pages/NomenclatureMapperPage.tsx",
        'Dutchie-to-METRC Nomenclature', '1 - Dutchie Catalog', '2 - Apply Names to METRC',
        'Mapping Library', 'Dutchie catalog export', 'METRC manifest export',
        'Ready', 'Needs Review', 'Unmatched', 'Create New Product',
        'Confirm & Remember Mappings', 'Correct_METRC_Item_Names.xlsx',
    )


def test_admin_integrations_location_and_facility_controls_survive_remigration():
    has(
        "frontend/src/pages/AdminPage.tsx",
        'User Management', 'Create User', 'Manage Existing', 'Temporary password',
        'Confirm temporary password', 'Require password change',
        'Platform Organizations & Facilities', 'Add Organization', 'Add Facility', 'facility_ids',
    )
    has(
        "frontend/src/pages/AdminToolsPage.tsx",
        'Facility license & operation context', 'License number', 'License type',
        'Production / Manufacturing', 'Cultivation', 'Commercial', 'Admin Uploads',
        'Operational diagnostics',
    )
    has(
        "frontend/src/pages/IntegrationsPage.tsx",
        'AI & METRC Integrations', 'METRC Integrations', 'METRC User API Key',
        'METRC State', 'METRC License / Facility', 'Doobie Service API Key',
        'Test Connection', 'Clear / Reset',
    )
    has(
        "frontend/src/pages/LocationSettingsPage.tsx",
        'Location Settings', 'Auto-map products during receive', 'Default receiving room',
        'Save location settings',
    )


def test_production_inventory_keeps_bulk_cultivation_plants_and_inventory_controls():
    has(
        "frontend/src/pages/InventoryPage.tsx",
        'Bulk cannabis materials, lots, rooms, receiving, transformations, and audits.',
        'All Material', 'Bulk Flower', 'Biomass / Trim', 'Extraction Input', 'WIP',
        'Finished Bulk', 'Production Ready', 'Low Balance', 'Quarantine / Hold',
        '<PlantInventory/>', 'Receive history', 'Receive inventory', 'Adjust', 'Package 360',
    )
    has(
        "frontend/src/components/PlantInventory.tsx",
        'clone', 'seedling', 'vegetative', 'flowering', 'harvested', 'destroyed',
        'Plant tag', 'Strain', 'Phase', 'Room', 'Mother', 'Lifecycle history',
        'Add plant', 'Record change',
    )
    has(
        "backend/app/auth.py",
        'require_inventory_operation_capability', '("production", "cultivation")',
        'get_production_context',
    )


def test_data_mode_is_propagated_to_the_api_and_buyer_workflow():
    has(
        "frontend/src/lib/api.ts",
        'buyer-dash-data-mode', 'X-DoobieLogic-Data-Mode',
    )
    has(
        "backend/app/auth.py",
        'normalized_data_mode', 'Dutchie Live', 'Uploads', 'X-DoobieLogic-Data-Mode',
    )
    has(
        "backend/app/routers/buyer_parity.py",
        'context.data_mode', 'Dutchie Live', 'live data fetch is not yet implemented',
    )


def test_executive_reports_reuse_streamlit_pdf_builders_and_active_buyer_scope():
    has(
        "backend/app/routers/executive_reports.py",
        '_build_buyer_executive_report_pdf', '_build_coman_executive_report_pdf',
        '_build_extraction_executive_report_pdf', '_build_white_label_repack_report_pdf',
        'combine_report_pdfs', 'Buyer Operations', 'Co-Man Production', 'Extraction Operations',
    )
    has(
        "frontend/src/pages/ExecutiveReportsPage.tsx",
        'Executive Reports', 'Retail Ops', 'Production Ops', 'Company',
        'Buyer Operations', 'Co-Man Production', 'Extraction Operations',
        'buyer-dash-buyer-controls',
    )


def test_real_browser_gate_covers_all_acceptance_widths_and_remaining_visual_workspaces():
    has(
        "frontend/e2e/parity-browser.spec.ts",
        'const WIDTHS = [390, 430, 768, 1024, 1440]',
        'Buyer Dashboard', 'Sales Trend', 'Revenue by Category', 'Top Slow Movers', 'Inventory Health',
        'White Label / Repack', 'Step 5: Compliance', 'Package Studio',
        'production-inventory-${width}', 'assertNoDocumentOverflow', 'saveEvidence',
    )
