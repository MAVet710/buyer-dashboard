from pathlib import Path

from modules.navigation.role_home import activate_home_action, actions_for_role
from services.workspace_navigation import apply_pending_workspace_navigation
from services.tenant_guard import TenantContext, tenant_access_issue
from services.upload_cache import load_cached_upload
from services.workspace_navigation import (
    COMAN_WORKSPACE,
    DATA_HUB_WORKSPACE,
    HOME_OPS,
    HOME_WORKSPACE,
    workspace_group,
    workspace_groups,
)


ROOT = Path(__file__).resolve().parents[1]


def test_operations_home_is_the_first_workspace_for_every_license():
    groups = workspace_groups(lambda name, default_enabled=True: True)

    assert list(groups)[0] == HOME_OPS
    assert groups[HOME_OPS] == [HOME_WORKSPACE]
    assert workspace_group(HOME_WORKSPACE) == HOME_OPS


def test_role_home_actions_are_filtered_and_navigate_atomically():
    buyer_actions = actions_for_role("buyer")
    assert any(action.workspace == DATA_HUB_WORKSPACE for action in buyer_actions)
    assert not any(action.workspace == COMAN_WORKSPACE for action in buyer_actions)

    target = next(action for action in buyer_actions if action.workspace == DATA_HUB_WORKSPACE)
    state = {"operations_group": "old", "workspace_mode": "old"}
    activate_home_action(state, target)
    assert state["operations_group"] == "old"
    assert apply_pending_workspace_navigation(state) is True
    assert state["operations_group"] == target.group
    assert state["workspace_mode"] == target.workspace


def test_tenant_owned_workspaces_fail_closed_without_context():
    assert tenant_access_issue(COMAN_WORKSPACE, TenantContext()) == (
        "Select an organization before opening this workspace."
    )
    assert tenant_access_issue(
        COMAN_WORKSPACE,
        TenantContext(organization_id="org-1"),
    ) == "Select a facility before opening this workspace."
    assert tenant_access_issue(
        COMAN_WORKSPACE,
        TenantContext(organization_id="org-1", facility_id="facility-1"),
    ) == ""
    assert tenant_access_issue(DATA_HUB_WORKSPACE, TenantContext()) == ""


def test_login_is_main_viewport_and_sidebar_uploaders_are_removed():
    login_source = (ROOT / "modules" / "authentication" / "login_page.py").read_text(
        encoding="utf-8"
    )
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "render_login_page(" in app_source
    assert "Keep shelves stocked, production moving, and chaos off the schedule." in login_source
    assert '[data-testid="stSidebar"]' in login_source
    assert 'st.sidebar.file_uploader(\n            "Inventory File' not in app_source
    assert '"Open Data Import Center"' in app_source


def test_current_user_guide_covers_every_operating_area():
    guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    for section in (
        "Retail Operations",
        "Production Operations",
        "Commercial Operations",
        "Data Import Center",
        "Roles",
        "Mobile use",
    ):
        assert section in guide


def test_reviewed_upload_cache_replays_file_without_streamlit_dependency():
    cached = load_cached_upload(
        {"_cache_inv": {"name": "inventory.csv", "bytes": b"Product,On Hand\nA,2\n"}},
        "_cache_inv",
    )

    assert cached is not None
    assert cached.name == "inventory.csv"
    assert cached.read().startswith(b"Product")
