from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_authenticated_app_uses_browser_history_with_spa_fallback():
    main = read("frontend/src/main.tsx")
    nginx = read("frontend/nginx.conf")

    assert 'import { BrowserRouter } from "react-router-dom"' in main
    assert "<BrowserRouter>" in main
    assert "try_files $uri $uri/ /index.html;" in nginx


def test_workspace_routes_cover_daily_jobs_and_manufacturing_distribution():
    routes = read("frontend/src/lib/workspaceRoutes.ts")

    for path in (
        "/home",
        "/buying",
        "/buying/purchase-orders",
        "/inventory",
        "/inventory/audits",
        "/production",
        "/production/extraction",
        "/production/orders",
        "/production/fulfillment",
        "/compliance",
        "/reports",
        "/settings/data",
    ):
        assert f'path: "{path}"' in routes

    for kind in ("product", "package", "production-run", "compliance-issue"):
        assert f'kind: "{kind}"' in routes


def test_app_preserves_legacy_pending_page_while_browser_history_becomes_authoritative():
    app = read("frontend/src/App.tsx")

    assert "useLocation" in app
    assert "useNavigate" in app
    assert "pageForPath(location.pathname)" in app
    assert "pathForPage(nextPage)" in app
    assert 'sessionStorage.getItem("buyer-dash-pending-page")' in app
    assert 'sessionStorage.removeItem("buyer-dash-pending-page")' in app
    pending_block = app.split('const pending = sessionStorage.getItem("buyer-dash-pending-page");', 1)[1].split('if (location.pathname === "/")', 1)[0]
    assert "if (pendingPath === location.pathname)" in pending_block
    assert pending_block.index("if (pendingPath === location.pathname)") < pending_block.index('sessionStorage.removeItem("buyer-dash-pending-page")')


def test_one_authoritative_operation_context_owns_inventory_mode():
    shell = read("frontend/src/components/AppShell.tsx")
    inventory = read("frontend/src/pages/InventoryPage.tsx")

    assert shell.count('aria-label="Operation"') == 1
    assert 'aria-label="Inventory operation"' not in inventory
    assert 'const operation:Operation=initialOperation' in inventory
    assert 'const [operation,setOperation]' not in inventory
    assert 'onNavigate?.("Inventory")' in inventory
    assert 'onNavigate?.("Production Inventory")' in inventory


def test_360_context_is_a_non_modal_workspace_window_not_a_blocking_page_requirement():
    window = read("frontend/src/components/WorkspaceWindow.tsx")
    window_css = read("frontend/src/components/workspace-window.css")
    product = read("frontend/src/components/Product360Drawer.tsx")
    package = read("frontend/src/components/Package360Window.tsx")
    inventory = read("frontend/src/pages/InventoryPage.tsx")
    app = read("frontend/src/App.tsx")
    contract = read("docs/UX_SIMPLIFICATION_EXECUTION_CONTRACT.md")

    assert 'aria-modal="false"' in window
    assert "Maximize2" in window
    assert "Minimize2" in window
    assert "workspace-window-minimize" in window
    assert "workspace-window-close" in window
    assert "onPointerDown={beginDrag}" in window
    assert "onPointerDownCapture={bringToFront}" in window
    assert "workspaceWindowRegistry" in window
    assert "topWorkspaceWindowKey() === windowKey" in window
    assert "workspaceWindowRegistry.delete(windowKey)" in window
    assert ".workspace-window.minimized" in window_css
    assert "backdrop-filter:blur(24px)" not in window_css
    assert "-webkit-backdrop-filter:blur(24px)" not in window_css
    assert "min-width:44px;min-height:44px" in window_css
    assert "<WorkspaceWindow" in product
    assert "<WorkspaceWindow" in package
    assert "<Package360Window" in product
    assert ">Product 360</button>" in inventory
    assert ">Package 360</button>" in inventory
    assert ">View lineage</button>" in inventory
    assert 'if (nextPage === "Production Run 360"' in app
    assert 'windowKey="production-run-360"' in app
    assert "Route = where I am working" in contract
    assert "Panel = what I am inspecting" in contract


def test_product_360_can_open_package_360_without_destroying_parent_workspace():
    product = read("frontend/src/components/Product360Drawer.tsx")

    assert 'const [package360,setPackage360]=useState("")' in product
    assert "onPackage={setPackage360}" in product
    assert "<Package360Window code={package360}" in product
    assert ">Package 360</button>" in product


def test_doobie_agent_uses_the_same_non_blocking_window_contract_as_360():
    agent = read("frontend/src/components/WorkspaceAgent.tsx")
    agent_css = read("frontend/src/components/workspace-agent.css")
    window = read("frontend/src/components/WorkspaceWindow.tsx")

    assert 'import { WorkspaceWindow } from "./WorkspaceWindow"' in agent
    assert "<WorkspaceWindow" in agent
    assert 'className="workspace-agent-window"' in agent
    assert 'aria-modal="false"' in window
    assert "workspace-agent-backdrop" not in agent
    assert "workspace-agent-backdrop" not in agent_css
    assert "createPortal" not in agent
    assert "Maximize2" not in agent
    assert "Minimize2" not in agent
    assert "workspace-window-close" in window
    assert "workspace-window-minimize" in window
    assert 'onClick={() => onNavigate("Integrations")}' in agent
    assert "top:max(6px,env(safe-area-inset-top))" in agent_css
    assert "bottom:max(6px,env(safe-area-inset-bottom))" in agent_css
    assert ".workspace-agent-window.minimized" in agent_css


def test_distribution_and_wholesale_are_embedded_in_production_not_new_primary_silo():
    shell = read("frontend/src/components/AppShell.tsx")
    contract = read("docs/UX_SIMPLIFICATION_EXECUTION_CONTRACT.md")

    production_primary = shell.split("const PRODUCTION_PRIMARY", 1)[1].split("function secondaryItems", 1)[0]
    assert 'label: "Distribution"' not in production_primary
    assert 'label: "Wholesale"' not in production_primary
    assert 'label: "Orders"' not in production_primary
    assert 'label: "Production"' in production_primary

    production_tools = shell.split('if (category === "Production") return [', 1)[1].split("];", 1)[0]
    for capability in ("Extraction", "Orders & Fulfillment", "Warehouse Pick / Pack", "White Label / Repack"):
        assert capability in production_tools

    assert "Distribution and wholesale are part of the manufacturing/Production operating model" in contract
