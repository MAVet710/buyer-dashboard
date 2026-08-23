from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shared_product_360_restores_the_streamlit_evidence_tabs_and_actions():
    drawer = read("frontend/src/components/Product360Drawer.tsx")
    inventory = read("frontend/src/pages/InventoryPage.tsx")
    search = read("frontend/src/components/GlobalSearch.tsx")
    home = read("frontend/src/pages/HomePage.tsx")

    assert '["Overview","Inventory","Sales","Purchasing","Packages","Compliance","Audits"]' in drawer
    assert "Suggested {data.decision.target_days}-day fill" in drawer
    assert "Add / update in PO" in drawer
    assert "Audit this SKU" in drawer
    assert "Open traceability" in drawer
    assert 'sessionStorage.setItem("buyer-dash-po-inventory-selection"' in drawer
    assert 'import { Product360Drawer } from "../components/Product360Drawer"' in inventory
    assert "function Product360Drawer(" not in inventory
    assert 'import { Product360Drawer } from "./Product360Drawer"' in search
    assert 'lotId={productLotId}' in home


def test_product_360_audit_focus_is_consumed_by_the_real_inventory_audit_workspace():
    drawer = read("frontend/src/components/Product360Drawer.tsx")
    focused = read("frontend/src/components/FocusedInventoryAudits.tsx")
    app = read("frontend/src/App.tsx")

    assert 'sessionStorage.setItem("buyer-dash-audit-product-focus"' in drawer
    assert 'sessionStorage.getItem("buyer-dash-audit-product-focus")' in focused
    assert 'row.product_id === focus?.product_id' in focused
    assert '"/api/v1/inventory/retail/audits"' in focused
    assert 'lot_ids: lots.map(row => row.id)' in focused
    assert "Start focused audit" in focused
    assert '<InventoryAudits operation="retail" />' in focused
    assert 'page === "Inventory Audits" ? <FocusedInventoryAudits />' in app


def test_product_360_backend_keeps_deterministic_streamlit_replenishment_economics():
    backend = read("backend/app/routers/product_360.py")
    main = read("backend/app/main.py")

    assert "TARGET_DAYS = 21" in backend
    assert "math.ceil(daily_velocity * TARGET_DAYS - on_hand)" in backend
    assert '"SELL-THROUGH REVIEW"' in backend
    assert '"ORDER NOW"' in backend
    assert '"REORDER"' in backend
    assert '"HEALTHY"' in backend
    assert "sales_windows[7]" in backend
    assert "sales_windows[30]" in backend
    assert 'for days in (7, 30, 60, 90)' in backend
    assert 'app.include_router(product_360_router' in main


def test_inventory_adjustment_restores_streamlit_traceability_controls_and_review_gate():
    web = read("frontend/src/components/AdjustInventory.tsx")
    router = read("backend/app/routers/inventory.py")
    schema = read("backend/app/schemas/inventory.py")

    for phrase in (
        "Adjustment type *",
        "Incremental",
        "Set Quantity",
        "Change (+ / -) *",
        "New quantity *",
        "Reason *",
        "Sync adjustment to Metrc",
        "Bypass state system",
        "I reviewed the package, final quantity, and adjustment reason.",
        "Adjust inventory",
    ):
        assert phrase in web
    assert 'import { StreamlitDialog } from "./StreamlitDialog"' in web
    assert "const canSubmit = reviewed &&" in web
    assert "setReviewed(false)" in web
    assert "reviewed," in web
    assert '@router.get("/{operation}/adjustment-reasons")' in router
    assert "fetch_package_adjustment_reasons" in router
    assert "run_tracked_metrc_adjustment" in router
    assert "backwards compatibility for existing" in router
    assert 'context.role.casefold() not in {"dev", "admin"}' in router
    assert "sync_to_metrc: bool = False" in schema
    assert "bypass_state_system: bool = False" in schema
    assert "reviewed: bool = True" in schema


def test_inventory_package_lineage_uses_the_same_streamlit_work_window_shell():
    lineage = read("frontend/src/components/PackageLineage.tsx")
    assert 'import { StreamlitDialog } from "./StreamlitDialog"' in lineage
    assert "<StreamlitDialog open" in lineage
    assert 'eyebrow="Package 360"' in lineage
    assert "Created from" in lineage
    assert "Used by" in lineage
