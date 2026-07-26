from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    PRODUCTION_OPS,
    RETAIL_OPS,
    WHITE_LABEL_WORKSPACE,
    buyer_section_options,
    workspace_group,
    workspace_groups,
    workspace_options,
)


def test_workspace_options_follow_license_features():
    enabled = lambda name, default_enabled=True: name == "buyer_module"
    options = workspace_options(enabled)
    assert COMAN_WORKSPACE in options
    assert COMMERCIAL_WORKSPACE in options
    assert DATA_HUB_WORKSPACE in options
    assert EXTRACTION_WORKSPACE not in options


def test_workspaces_are_grouped_by_operating_area():
    enabled = lambda name, default_enabled=True: name in {
        "buyer_module",
        "extraction_module",
    }

    groups = workspace_groups(enabled)

    assert groups[RETAIL_OPS] == [BUYER_WORKSPACE, WHITE_LABEL_WORKSPACE]
    assert groups[PRODUCTION_OPS] == [COMAN_WORKSPACE, EXTRACTION_WORKSPACE]
    assert groups[COMMERCIAL_OPS] == [COMMERCIAL_WORKSPACE]
    assert groups[DATA_OPERATIONS] == [DATA_HUB_WORKSPACE]


def test_saved_workspace_resolves_to_its_operations_group():
    assert workspace_group(BUYER_WORKSPACE) == RETAIL_OPS
    assert workspace_group(WHITE_LABEL_WORKSPACE) == RETAIL_OPS
    assert workspace_group(COMAN_WORKSPACE) == PRODUCTION_OPS
    assert workspace_group(EXTRACTION_WORKSPACE) == PRODUCTION_OPS
    assert workspace_group(COMMERCIAL_WORKSPACE) == COMMERCIAL_OPS
    assert workspace_group(DATA_HUB_WORKSPACE) == DATA_OPERATIONS


def test_admin_sections_are_role_aware():
    standard = buyer_section_options(is_admin=False)
    admin = buyer_section_options(is_admin=True)
    assert "🛠️ Admin Tools" not in standard
    assert "🔌 Integrations" not in standard
    assert "🛠️ Admin Tools" in admin
    assert "🔌 Integrations" in admin


def test_nomenclature_mapper_is_available_to_buyer_operations_users():
    standard = buyer_section_options(is_admin=False)

    assert "🏷️ Nomenclature Mapper" in standard
