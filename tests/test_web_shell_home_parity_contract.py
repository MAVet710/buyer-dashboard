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


def test_flat_shell_matches_streamlit_category_order_context_search_and_compatibility():
    streamlit_nav = read("services/workspace_navigation.py")
    streamlit_shell = read("modules/navigation/workspace_shell.py")
    shell = read("frontend/src/components/AppShell.tsx")

    categories = ["Home", "Inventory", "Purchasing", "Orders", "Production", "Reports", "Compliance", "Data & Settings"]
    for category in categories:
        assert f'"{category}"' in streamlit_nav
        assert f'label: "{category}"' in shell

    retail_order = ["Home", "Inventory", "Purchasing", "Orders", "Reports", "Compliance", "Data & Settings"]
    retail_block = shell.split("const RETAIL_PRIMARY", 1)[1].split("const PRODUCTION_PRIMARY", 1)[0]
    assert [retail_block.index(f'label: "{label}"') for label in retail_order] == sorted(retail_block.index(f'label: "{label}"') for label in retail_order)

    production_order = ["Home", "Inventory", "Production", "Orders", "Compliance", "Data & Settings"]
    production_block = shell.split("const PRODUCTION_PRIMARY", 1)[1].split("function secondaryItems", 1)[0]
    assert [production_block.index(f'label: "{label}"') for label in production_order] == sorted(production_block.index(f'label: "{label}"') for label in production_order)

    for contract in (
        'aria-label="Organization"',
        'aria-label="Facility"',
        'aria-label="Operation"',
        "<GlobalSearch onNavigate={navigate}/>",
        "Use classic navigation",
        'className="dl-nav-context"',
    ):
        assert contract in shell
    assert "flat_nav_tool_label" in streamlit_shell
    assert "buyer_dash_global_search" in streamlit_shell


def test_mobile_navigation_preserves_streamlit_category_tool_and_buyer_source_selectors():
    streamlit = read("modules/navigation/workspace_shell.py")
    shell = read("frontend/src/components/AppShell.tsx")

    assert 'aria-label="Navigate"' in shell
    assert 'aria-label="Tool"' in shell
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
