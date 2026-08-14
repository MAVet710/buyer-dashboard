from services.workspace_navigation import (
    AI_INTEGRATIONS_SECTION,
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    METRC_INTEGRATIONS_SECTION,
    EXTRACTION_WORKSPACE,
    HOME_OPS,
    HOME_WORKSPACE,
    INVENTORY_COUNTS_SECTION,
    MA_FLOWER_EQUIVALENCY_SECTION,
    PRODUCTION_OPS,
    RETAIL_OPS,
    WHITE_LABEL_WORKSPACE,
    buyer_section_options,
    buyer_section_groups,
    can_manage_ai_integrations,
    workspace_group,
    workspace_groups,
    workspace_options,
)


def test_workspace_options_follow_license_features():
    enabled = lambda name, default_enabled=True: name == "buyer_module"
    options = workspace_options(enabled)
    assert HOME_WORKSPACE in options
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

    assert groups[HOME_OPS] == [HOME_WORKSPACE]
    assert groups[RETAIL_OPS] == [BUYER_WORKSPACE, WHITE_LABEL_WORKSPACE]
    assert groups[PRODUCTION_OPS] == [COMAN_WORKSPACE, EXTRACTION_WORKSPACE]
    assert groups[COMMERCIAL_OPS] == [COMMERCIAL_WORKSPACE]
    assert groups[DATA_OPERATIONS] == [DATA_HUB_WORKSPACE]


def test_saved_workspace_resolves_to_its_operations_group():
    assert workspace_group(HOME_WORKSPACE) == HOME_OPS
    assert workspace_group(BUYER_WORKSPACE) == RETAIL_OPS
    assert workspace_group(WHITE_LABEL_WORKSPACE) == RETAIL_OPS
    assert workspace_group(COMAN_WORKSPACE) == PRODUCTION_OPS
    assert workspace_group(EXTRACTION_WORKSPACE) == PRODUCTION_OPS
    assert workspace_group(COMMERCIAL_WORKSPACE) == COMMERCIAL_OPS
    assert workspace_group(DATA_HUB_WORKSPACE) == DATA_OPERATIONS


def test_admin_sections_are_role_aware():
    standard = buyer_section_options(is_admin=False, user_role="buyer")
    admin = buyer_section_options(is_admin=True, user_role="admin")
    developer = buyer_section_options(is_admin=True, user_role="dev")
    assert "🛠️ Admin Tools" not in standard
    assert METRC_INTEGRATIONS_SECTION in standard
    assert AI_INTEGRATIONS_SECTION not in standard
    assert "🛠️ Admin Tools" in admin
    assert METRC_INTEGRATIONS_SECTION in admin
    assert AI_INTEGRATIONS_SECTION not in admin
    assert AI_INTEGRATIONS_SECTION in developer
    assert METRC_INTEGRATIONS_SECTION not in developer


def test_only_level_dev_can_manage_ai_integrations():
    assert can_manage_ai_integrations("dev") is True
    for role in [
        "admin",
        "buyer",
        "planner",
        "supervisor",
        "operator",
        "qa",
        "read_only",
        "trial",
        None,
    ]:
        assert can_manage_ai_integrations(role) is False


def test_nomenclature_mapper_is_available_to_buyer_operations_users():
    standard = buyer_section_options(is_admin=False)

    assert "🏷️ Nomenclature Mapper" in standard


def test_inventory_counts_are_available_to_retail_users():
    standard = buyer_section_options(is_admin=False, user_role="buyer")

    assert INVENTORY_COUNTS_SECTION in standard


def test_buyer_tools_are_grouped_into_compact_retail_areas():
    groups = buyer_section_groups(is_admin=False, user_role="buyer")

    assert list(groups) == [
        "Overview",
        "Inventory",
        "Purchasing",
        "Compliance",
        "Administration",
    ]
    assert INVENTORY_COUNTS_SECTION in groups["Inventory"]
    assert MA_FLOWER_EQUIVALENCY_SECTION in groups["Inventory"]
    assert METRC_INTEGRATIONS_SECTION in groups["Administration"]


def test_ma_flower_equivalency_is_available_to_retail_users():
    standard = buyer_section_options(is_admin=False, user_role="buyer")

    assert MA_FLOWER_EQUIVALENCY_SECTION in standard
