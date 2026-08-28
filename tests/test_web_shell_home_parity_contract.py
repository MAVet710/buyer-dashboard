from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_react_operation_roles_match_streamlit_operation_context_contract():
    streamlit = read("modules/navigation/operation_context_bar.py")
    shell = read("frontend/src/components/AppShell.tsx")

    assert '"planner"' not in shell.split("const RETAIL_ROLES =", 1)[1].split("as const", 1)[0]
    production_roles = shell.split("const PRODUCTION_ROLES =", 1)[1].split("as const", 1)[0]
    assert '"read_only"' not in production_roles
    assert '"trial"' not in production_roles
    for role in ("dev", "admin", "buyer", "supervisor", "operator", "qa", "read_only"):
        assert f'"{role}"' in streamlit
    assert 'const RETAIL_ROLES = ["dev", "admin", "buyer", "supervisor", "operator", "qa", "read_only", "trial"]' in shell
    assert 'const PRODUCTION_ROLES = ["dev", "admin", "planner", "supervisor", "operator", "qa"]' in shell


def test_job_first_shell_preserves_context_search_and_promotes_wholesale_ops():
    shell = read("frontend/src/components/AppShell.tsx")
    contract = read("docs/UX_SIMPLIFICATION_EXECUTION_CONTRACT.md")

    retail_order = ["Home", "Buying", "Inventory", "Wholesale", "Compliance", "Reports"]
    retail_block = shell.split("const RETAIL_PRIMARY", 1)[1].split("const PRODUCTION_PRIMARY", 1)[0]
    assert [retail_block.index(f'label: "{label}"') for label in retail_order] == sorted(retail_block.index(f'label: "{label}"') for label in retail_order)
    assert 'label: "Orders"' not in retail_block
    assert 'label: "Data & Settings"' not in retail_block

    production_order = ["Home", "Inventory", "Production", "Wholesale", "Compliance", "Reports"]
    production_block = shell.split("const PRODUCTION_PRIMARY", 1)[1].split("function secondaryItems", 1)[0]
    assert [production_block.index(f'label: "{label}"') for label in production_order] == sorted(production_block.index(f'label: "{label}"') for label in production_order)
    assert 'label: "Orders"' not in production_block
    assert 'label: "Data & Settings"' not in production_block

    production_secondary = shell.split('if (category === "Production") return [', 1)[1].split("];", 1)[0]
    for capability in ("Extraction", "White Label / Repack", "Production Run 360"):
        assert capability in production_secondary
    assert "Orders & Fulfillment" not in production_secondary
    assert "Warehouse Pick / Pack" not in production_secondary

    wholesale_secondary = shell.split('if (category === "Wholesale") return [', 1)[1].split("];", 1)[0]
    for capability in ("Wholesale Ops", "Orders", "Fulfillment"):
        assert capability in wholesale_secondary

    for contract_text in (
        'aria-label="Organization"',
        'aria-label="Facility"',
        'aria-label="Operation"',
        "<GlobalSearch onNavigate={navigate}/>",
        "Use classic navigation",
        'className="dl-nav-context"',
        "Settings & Administration",
        "Wholesale Ops",
    ):
        assert contract_text in shell

    assert "Wholesale Ops is a first-class commercial workspace" in contract
    assert "Production remains the manufacturing source of truth" in contract
    assert "Route = where I am working" in contract
    assert "Panel = what I am inspecting" in contract
    assert "Dialog = what I am doing" in contract


def test_mobile_navigation_preserves_category_tool_buyer_source_and_settings_access():
    streamlit = read("modules/navigation/workspace_shell.py")
    shell = read("frontend/src/components/AppShell.tsx")

    assert 'aria-label="Navigate"' in shell
    assert 'aria-label="Tool"' in shell
    assert 'aria-label="Settings and administration"' in shell
    assert 'className="mobile-data-mode-select"' in shell
    assert 'aria-label="Buyer data mode"' in shell
    assert '<option value="Uploads">📁 Uploads</option>' in shell
    assert '<option value="Dutchie Live">🔴 Dutchie Live</option>' in shell
    assert 'operation === "Retail Ops"' in shell
    assert 'onDataMode(event.target.value === "Dutchie Live" ? "Dutchie Live" : "Uploads")' in shell
    assert 'modes = ["📁 Uploads", "🔴 Dutchie Live"]' in streamlit
    assert "mobile_flat_nav_data_mode" in streamlit


def test_home_restores_role_aware_streamlit_decision_surface():
    streamlit = read("modules/navigation/role_home.py")
    home = read("frontend/src/pages/HomePage.tsx")
    backend = read("backend/app/routers/home.py")

    for label in (
        "Review inventory",
        "Start inventory audit",
        "Traceability queue",
        "Open Package Studio",
        "Build purchasing decisions",
        "Plan Co-Man production",
        "Review extraction",
        "Manage orders",
        "Import operational data",
    ):
        assert label in streamlit
        assert label in home
    for metric in ("Needs attention", "Low stock", "Open POs", "Data sources ready"):
        assert metric in streamlit
        assert metric in home
    for field in ("low_stock", "open_purchase_orders", "open_purchase_order_value", "data_sources_total"):
        assert field in backend


def test_buyer_command_center_keeps_recorded_overview_inside_primary_workflow():
    buyer = unescape(read("frontend/src/pages/BuyerOperationsPage.tsx"))
    overview = read("frontend/src/components/BuyerLegacyOverview.tsx")

    assert "<BuyerLegacyOverview" in buyer
    for label in ("Sales Trend", "Revenue by Category", "Inventory Health", "Top Slow Movers", "Inventory Summary"):
        assert label in overview
    for label in ("Category DOS (at a glance)", "Forecast Table", "Buyer Filters & Settings", "Doobie Inventory Check", "Doobie Buyer Brief"):
        assert label in buyer
