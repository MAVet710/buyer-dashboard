from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_react_audit_workspace_preserves_streamlit_source_order_and_controls():
    source = (ROOT / "frontend" / "src" / "components" / "InventoryAudits.tsx").read_text(encoding="utf-8")
    labels = [
        "Retail Scan Audit",
        "Inventory Audit & Reconciliation",
        "Each audit is an independent saved workspace.",
        "Load or refresh Dutchie retail inventory",
        "Inventory source",
        "Upload Dutchie inventory export",
        "Use active Buyer Ops inventory",
        "Dutchie inventory file",
        "Import & Use for Next Audit",
        "Start New Audit",
        "Audit name / number",
        "Scope",
        "Inventory to count",
        "Blind first count",
        "Recount tolerance",
        "Notes (optional)",
        "Audit Dashboard",
        "Products scanned",
        "Remaining",
        "Recounts",
        "Scan exceptions",
        "Back to Dashboard",
        "Pause Audit",
        "Stop & Review",
        "Generate Current Report",
        "Scan and count",
        "Recount scanner",
        "Bluetooth / USB scanner or typed code",
        "Scan or enter item code",
        "Cannot scan? Choose the inventory item",
        "Enter count for selected item",
        "Enter inventory count",
        "Physical quantity in stock",
        "Variance reason",
        "Count note (optional)",
        "Save & scan next",
        "Complete Audit",
        "Reopen Audit",
        "Resume Audit",
        "Audit Report",
        "Export CSV",
        "Export Excel",
        "Activity log",
    ]
    for value in labels:
        assert value in source
    for heading in ["Active", "Paused", "Stopped", "Completed", "Cancelled"]:
        assert f'["{heading}"' in source
    assert "{heading} Audits" in source
    ordered = ["Load or refresh Dutchie retail inventory", "Start New Audit", "Audit Dashboard"]
    assert [source.index(value) for value in ordered] == sorted(source.index(value) for value in ordered)
    assert 'title="Enter inventory count"' in source
    assert 'title="Inventory audits"' not in source


def test_inventory_audit_routes_use_durable_scoped_repository_and_reports():
    router = (ROOT / "backend" / "app" / "routers" / "audits.py").read_text(encoding="utf-8")
    service = (ROOT / "backend" / "app" / "services" / "audits.py").read_text(encoding="utf-8")
    for contract in [
        "require_operation_capability",
        '"buyer"',
        '"trial"',
        '@router.post("/{audit_id}/scan/preview"',
        '@router.post("/{audit_id}/scan/count"',
        '@router.get("/{audit_id}/report.csv")',
        '@router.get("/{audit_id}/report.xlsx")',
        '@router.post("/retail-snapshot/preview")',
        '@router.post("/retail-snapshot/import")',
        "import_retail_snapshot",
    ]:
        assert contract in router
    assert "record_scanned_count" in router
    assert "get_audit_events" in service
    assert 'status="in_progress"' in service


def test_inventory_audit_is_a_workspace_and_inventory_action_routes_to_it():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    inventory = (ROOT / "frontend" / "src" / "pages" / "InventoryPage.tsx").read_text(encoding="utf-8")
    focused = (ROOT / "frontend" / "src" / "components" / "FocusedInventoryAudits.tsx").read_text(encoding="utf-8")
    assert 'page === "Inventory Audits" ? <FocusedInventoryAudits />' in app
    assert '<InventoryAudits operation={operation} />' in focused
    assert 'type Operation = "retail" | "production"' in focused
    assert 'sessionStorage.getItem("buyer-dash-audit-product-focus")' in focused
    assert '`/api/v1/inventory/${operation}/audits`' in focused
    assert 'onNavigate?.("Inventory Audits")' in inventory
    assert "<InventoryAudits operation={operation}" not in inventory
