from services.workspace_navigation import (
    COMAN_WORKSPACE,
    EXTRACTION_WORKSPACE,
    buyer_section_options,
    workspace_options,
)


def test_workspace_options_follow_license_features():
    enabled = lambda name, default_enabled=True: name == "buyer_module"
    options = workspace_options(enabled)
    assert COMAN_WORKSPACE in options
    assert EXTRACTION_WORKSPACE not in options


def test_admin_sections_are_role_aware():
    standard = buyer_section_options(is_admin=False)
    admin = buyer_section_options(is_admin=True)
    assert "🛠️ Admin Tools" not in standard
    assert "🔌 Integrations" not in standard
    assert "🛠️ Admin Tools" in admin
    assert "🔌 Integrations" in admin
