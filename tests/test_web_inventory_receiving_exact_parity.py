from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_retail_receive_preserves_streamlit_inbound_queue_details_review_post_labels_flow():
    source = read("modules/inventory_receiving.py")
    web = read("frontend/src/components/ReceiveInventory.tsx")

    for label in (
        "Inbound Queue",
        "Receive Details",
        "Review",
        "Post Inventory",
        "Labels",
        "Get Metrc Lab Results",
    ):
        assert label in source
        assert label in web or label == "Get Metrc Lab Results" and "Pull read-only METRC lab results" in web

    assert "Inbound Queue → Receive Details → Review → Post Inventory → Labels" in web
    assert "Traceability is read-only in this work window." in web
    assert 'queryKey: ["inventory-inbound", operation]' in web
    assert 'queryKey: ["inventory-receive-history", operation]' in web
    assert "/receipts/batch" in web
    assert "one atomic transaction" in web


def test_production_receive_is_a_separate_bulk_material_workflow():
    source = read("modules/production_inventory_receiving.py")
    web = read("frontend/src/components/ProductionReceiveInventory.tsx")

    for label in (
        "PRODUCTION / CULTIVATION RECEIVING",
        "Receive material",
        "Material / product",
        "METRC package ID",
        "Internal lot / batch",
        "Quantity",
        "Unit",
        "Room / location",
        "Source facility / supplier",
        "Manifest / transfer #",
        "Notes",
    ):
        assert label in source
        assert label in web
    assert "Retail inventory is never modified." in source
    assert "Retail inventory is never modified." in web
    assert '"/api/v1/inventory/production/receipts"' in web
    assert "ReceiveInventory" not in web


def test_receive_history_is_operation_and_facility_scoped_with_streamlit_receipt_evidence():
    web = read("frontend/src/components/ReceiveHistory.tsx")
    backend = read("backend/app/routers/inventory.py")

    for label in ("Receive history", "Received", "Product", "Package", "Quantity", "Source", "Manifest", "Actor"):
        assert label in web
    assert '`/api/v1/inventory/${operation}/receive-history`' in web
    assert "context.organization_id" in backend
    assert "context.facility_id" in backend


def test_inventory_selection_actions_remain_in_one_command_center():
    web = read("frontend/src/pages/InventoryPage.tsx")
    for label in (
        "Product 360",
        "Audit",
        "Add to PO",
        "Package Studio",
        "Print labels",
        "Adjust",
        "Export selected",
    ):
        assert label in web
    assert "selectedIds" in web
    assert "StreamlitDialog" in web
