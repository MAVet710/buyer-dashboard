from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_global_shell_home_and_drawer_contracts_remain_streamlit_shaped():
    shell = read("frontend/src/components/AppShell.tsx")
    dialog = read("frontend/src/components/StreamlitDialog.tsx")
    css = read("frontend/src/streamlit-exact.css")
    home = read("frontend/src/pages/HomePage.tsx")
    product = read("frontend/src/components/Product360Drawer.tsx")

    for label in ("Home", "Inventory", "Purchasing", "Orders", "Production", "Reports", "Compliance", "Data & Settings"):
        assert label in shell
    for label in ("Retail Ops", "Production Ops", "Organization", "Facility", "Operation", "Uploads", "Dutchie Live"):
        assert label in shell
    assert "GlobalSearch" in shell
    assert "classicNavigation" in shell
    assert "MobileNavigation" in shell
    assert 'window.dispatchEvent(new CustomEvent("buyer-dash-data-mode"' in shell
    assert 'role="dialog"' in dialog
    assert ".modal{position:fixed!important;top:0!important;right:0!important" in css
    assert "@media(max-width:900px)" in css
    assert "max-width:none!important;height:100dvh" in css
    for tab in ("Overview", "Inventory", "Sales", "Purchasing", "Packages", "Compliance", "Audits"):
        assert tab in product
    assert "Product360Drawer" in home


def test_inventory_actions_receiving_and_operation_aware_audits_are_one_workflow():
    page = read("frontend/src/pages/InventoryPage.tsx")
    retail_receive = read("frontend/src/components/ReceiveInventory.tsx")
    production_receive = read("frontend/src/components/ProductionReceiveInventory.tsx")
    focus = read("frontend/src/components/FocusedInventoryAudits.tsx")
    history = read("frontend/src/components/ReceiveHistory.tsx")

    for label in ("Product 360", "Audit", "Add to PO", "Work on package", "Print labels", "Adjust", "Export selected", "Package 360"):
        assert label in page
    assert 'initialLotId={actionPackage?.id}' in page
    assert 'const selectedPackages=grain==="packages"?selected:packageRows.filter' in page
    assert 'setPackageChoice(action)' in page
    assert "Inbound Queue → Receive Details → Review → Post Inventory → Labels" in retail_receive
    assert "PRODUCTION / CULTIVATION RECEIVING" in production_receive
    assert "Retail inventory is never modified." in production_receive
    assert 'type Operation = "retail" | "production"' in focus
    assert '`/api/v1/inventory/${operation}/packages?view=all`' in focus
    assert '`/api/v1/inventory/${operation}/audits`' in focus
    assert '<InventoryAudits operation={operation} />' in focus
    assert '`/api/v1/inventory/${operation}/receive-history`' in history


def test_production_inventory_preserves_material_plant_adjustment_lineage_and_hold_semantics():
    page = read("frontend/src/pages/InventoryPage.tsx")
    plants = read("frontend/src/components/PlantInventory.tsx")
    adjust = read("frontend/src/components/AdjustInventory.tsx")
    lineage = read("frontend/src/components/PackageLineage.tsx")
    service = read("backend/app/services/inventory.py")

    assert 'const PRODUCTION_VIEWS = ["All Material", "Bulk Flower", "Biomass / Trim", "Extraction Input", "WIP", "Finished Bulk", "Production Ready", "Low Balance", "Quarantine / Hold"]' in page
    assert '<PlantInventory/>' in page
    assert "Plant 360" in plants and "Lifecycle history" in plants
    assert 'operation: "retail" | "production"' in adjust
    assert "Incremental" in adjust and "Set Quantity" in adjust
    assert "Sync adjustment to Metrc" in adjust
    assert 'operation: "retail" | "production"' in lineage
    assert "Created from" in lineage and "Used by" in lineage
    assert 'attention = "Hold"' in service
    assert 'view_key in {"hold", "quarantine-hold"}' in service
    assert 'sold_30d if operation == "retail" else 0.0' in service


def test_admin_compliance_mapper_location_and_buyer_source_contracts_are_present():
    admin = read("frontend/src/pages/AdminPage.tsx")
    admin_tools = read("frontend/src/pages/AdminToolsPage.tsx")
    integrations = read("frontend/src/pages/IntegrationsPage.tsx")
    compliance = read("frontend/src/pages/ComplianceQAPage.tsx")
    mapper = read("frontend/src/pages/NomenclatureMapperPage.tsx")
    location = read("frontend/src/pages/LocationSettingsPage.tsx")
    data_mode = read("backend/app/routers/buyer_parity.py")

    for label in ("Create User", "Manage Existing", "Facility access", "Reset Password"):
        assert label in admin
    assert "Admin Uploads" in admin_tools and "Operational diagnostics" in admin_tools
    assert "METRC Integrations" in integrations and "Clear / Reset" in integrations
    assert "Compliance Q&amp;A" in compliance
    assert "source_citation" in compliance and "review_status" in compliance
    assert "Review suggested names" in mapper and "Mapping Library" in mapper
    assert "Download Dutchie product names" in mapper
    assert "DATA & SETTINGS / LOCATION" in location
    assert "Auto-map never guesses a new catalog relationship." in location
    assert "_require_available_data_mode" in data_mode


def test_report_pack_uses_active_buyer_controls_and_only_current_streamlit_report_builders():
    web = read("frontend/src/pages/ExecutiveReportsPage.tsx")
    backend = read("backend/app/routers/executive_reports.py")
    app = read("app.py")

    for label in ("Download Retail Ops Pack", "Download Production Ops Pack", "Download Company Executive Pack"):
        assert label in web and label in app
    assert 'sessionStorage.getItem("buyer-dash-buyer-controls")' in web
    assert "controls = _buyer_controls(payload)" in backend
    for builder in ("_build_buyer_executive_report_pdf", "_build_white_label_repack_report_pdf", "_build_coman_executive_report_pdf", "_build_extraction_executive_report_pdf"):
        assert builder in backend
    # The legacy labor/competitor builders remain conditional pack additions in
    # Streamlit session state; they are not standalone flat-nav report routes.
    assert '"retail_ops_labor_report_bytes"' in app
    assert '"retail_ops_competitor_report_bytes"' in app
