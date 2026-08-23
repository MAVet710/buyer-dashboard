from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_react_commercial_workspace_matches_streamlit_tabs_and_source_controls():
    source = (ROOT / "frontend" / "src" / "pages" / "OrdersPage.tsx").read_text(encoding="utf-8")
    for label in [
        "Orders, inventory, and fulfillment",
        "One durable flow from purchase order to receipt, reservation, shipment, and payment.",
        "Command Center",
        "New Order",
        "Allocate & Fulfill",
        "Trade Partners",
        "Inventory Audits",
        "Inventory Ledger",
        "Active inventory",
        "Open sales",
        "Open purchases",
        "Fill rate",
        "Exceptions",
        "Search orders",
        "Incoming purchase orders",
        "Outgoing sales orders",
        "Inventory & due-date exceptions",
        "Create an order",
        "Order type",
        "Order number",
        "Order date",
        "Due date",
        "External reference",
        "Line notes",
        "Order notes",
        "Create draft order",
        "Open order",
        "Confirm order",
        "Payment",
        "Update payment",
        "Cancel order",
        "Line to process",
        "Inventory lot",
        "Fulfillment reference",
        "Reserve lot",
        "Post shipment",
        "Post receipt",
        "Add trade partner",
        "Partner directory",
        "Commercial inventory ledger",
        "Export ledger CSV",
        "Wholesale + Finance",
        "Order → allocation → shipment → invoice → payment, without leaving the commercial workflow.",
        "Sales Orders",
        "A/R",
        "Open order finance",
        "Shipment / manifest",
        "Shipment number",
        "State manifest reference",
        "Carrier / route",
        "Create shipment",
        "Invoice / payment",
        "Invoice number",
        "Due in days",
        "Create invoice from order",
        "Mark invoice sent",
        "Post payment",
        "Customer-specific pricing",
        "Fixed wholesale price",
        "Or discount %",
        "Save price rule",
    ]:
        assert label in source
    assert "modal-backdrop" not in source
    assert "Order 360" not in source
    assert source.index("Command Center") < source.index("Inventory Ledger")


def test_commercial_workspace_uses_durable_scoped_services_and_embedded_audits():
    router = (ROOT / "backend" / "app" / "routers" / "commercial.py").read_text(encoding="utf-8")
    audits = (ROOT / "frontend" / "src" / "components" / "InventoryAudits.tsx").read_text(encoding="utf-8")
    for contract in [
        '@router.get("/workspace")',
        "commercial_dashboard_metrics",
        "list_commercial_transactions",
        '@router.post("/orders/{order_id}/payment")',
        '@router.post("/inventory-lots"',
        '@router.post("/customer-prices"',
        "CommercialFinanceService",
        "context.organization_id",
        "context.facility_id",
    ]:
        assert contract in router
    assert "embedded = false" in audits
    assert 'embedded?"embedded-audits exact-audits":"page exact-audits"' in audits
