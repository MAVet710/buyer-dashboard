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
    buyer = read("frontend/src/pages/BuyerOperationsPage.tsx")
    overview = read("frontend/src/components/BuyerLegacyOverview.tsx")

    assert "<BuyerLegacyOverview" in buyer
    for label in ("Sales Trend", "Revenue by Category", "Inventory Health", "Top Slow Movers", "Inventory Summary"):
        assert label in overview
    for label in ("Category DOS (at a glance)", "Forecast Table", "Buyer Filters & Settings", "Doobie Inventory Check", "Doobie Buyer Brief"):
        assert label in buyer
