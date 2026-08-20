from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:140]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# services/workspace_navigation.py
replace_once(
    "services/workspace_navigation.py",
    'MA_FLOWER_EQUIVALENCY_SECTION = "🌿 MA Flower Equivalency"\n',
    'MA_FLOWER_EQUIVALENCY_SECTION = "🌿 MA Flower Equivalency"\n'
    'INVENTORY_COMMAND_CENTER_SURFACE = "inventory_command_center"\n',
)
replace_once(
    "services/workspace_navigation.py",
    '    "📊 Inventory Dashboard": "Inventory",\n',
    '    "📊 Inventory Dashboard": "Purchasing",\n',
)
replace_once(
    "services/workspace_navigation.py",
    '    "📊 Inventory Dashboard": "Inventory Overview",\n',
    '    "📊 Inventory Dashboard": "Overview",\n',
)
replace_once(
    "services/workspace_navigation.py",
    '''        "Overview": [\n            "📊 Inventory Dashboard",\n            "📈 Trends",\n            "🧠 Buyer Intelligence",\n        ],\n''',
    '''        "Overview": [\n            "📈 Trends",\n        ],\n''',
)
replace_once(
    "services/workspace_navigation.py",
    '''        "Purchasing": [\n            "🚚 Delivery Impact",\n            "🧾 PO Builder",\n            "💰 Purchasing Budget",\n        ],\n''',
    '''        "Purchasing": [\n            "📊 Inventory Dashboard",\n            "🧠 Buyer Intelligence",\n            "🚚 Delivery Impact",\n            "🧾 PO Builder",\n            "💰 Purchasing Budget",\n        ],\n''',
)

# modules/navigation/workspace_shell.py
replace_once(
    "modules/navigation/workspace_shell.py",
    '    HOME_WORKSPACE,\n    PRODUCTION_OPS,\n',
    '    HOME_WORKSPACE,\n    INVENTORY_COMMAND_CENTER_SURFACE,\n    PRODUCTION_OPS,\n',
)
replace_once(
    "modules/navigation/workspace_shell.py",
    '    if category != "Data & Settings":\n        state.pop("flat_virtual_surface", None)\n',
    '    if category not in {"Data & Settings", "Inventory"}:\n        state.pop("flat_virtual_surface", None)\n',
)
replace_once(
    "modules/navigation/workspace_shell.py",
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        workspace = _production_workspace(workspaces)\n        if workspace:\n            _set_production_route(state, workspace)\n        return\n\n    if category in {"Inventory", "Purchasing", "Reports", "Compliance"} and BUYER_WORKSPACE in workspaces:\n''',
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        workspace = _production_workspace(workspaces)\n        if workspace:\n            _set_production_route(state, workspace)\n        return\n\n    if category == "Inventory" and BUYER_WORKSPACE in workspaces:\n        state["flat_virtual_surface"] = INVENTORY_COMMAND_CENTER_SURFACE\n        state["operations_group"] = RETAIL_OPS\n        state["workspace_mode"] = BUYER_WORKSPACE\n        return\n\n    if category in {"Purchasing", "Reports", "Compliance"} and BUYER_WORKSPACE in workspaces:\n''',
)
replace_once(
    "modules/navigation/workspace_shell.py",
    '''        preferred = {\n            "Inventory": INVENTORY_DASHBOARD_SECTION,\n            "Purchasing": "🧾 PO Builder",\n            "Reports": "📈 Trends",\n''',
    '''        preferred = {\n            "Purchasing": INVENTORY_DASHBOARD_SECTION,\n            "Reports": "📈 Trends",\n''',
)
replace_once(
    "modules/navigation/workspace_shell.py",
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        return []\n    if category in {"Inventory", "Purchasing", "Reports", "Compliance"}:\n        return [\n            (buyer_section_display_name(section), "section", section)\n            for section in flat_buyer_sections(category, dict(section_groups))\n        ]\n''',
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        return []\n    if category == "Inventory":\n        return [("Inventory", "virtual", INVENTORY_COMMAND_CENTER_SURFACE)] + [\n            (buyer_section_display_name(section), "section", section)\n            for section in flat_buyer_sections(category, dict(section_groups))\n        ]\n    if category in {"Purchasing", "Reports", "Compliance"}:\n        return [\n            (buyer_section_display_name(section), "section", section)\n            for section in flat_buyer_sections(category, dict(section_groups))\n        ]\n''',
)
replace_once(
    "modules/navigation/workspace_shell.py",
    '''    if (\n        operation_mode == PRODUCTION_OPERATION\n        and requested_category == "Inventory"\n        and "Inventory" in available\n    ):\n        inferred = "Inventory"\n        _default_route_for_category(state, "Inventory", groups, section_groups)\n    elif requested_category == "Data & Settings" and state.get("flat_virtual_surface") == LOCATION_SETTINGS_SURFACE:\n''',
    '''    if (\n        operation_mode == PRODUCTION_OPERATION\n        and requested_category == "Inventory"\n        and "Inventory" in available\n    ):\n        inferred = "Inventory"\n        _default_route_for_category(state, "Inventory", groups, section_groups)\n    elif (\n        operation_mode != PRODUCTION_OPERATION\n        and requested_category == "Inventory"\n        and state.get("flat_virtual_surface") == INVENTORY_COMMAND_CENTER_SURFACE\n        and "Inventory" in available\n    ):\n        inferred = "Inventory"\n    elif requested_category == "Data & Settings" and state.get("flat_virtual_surface") == LOCATION_SETTINGS_SURFACE:\n''',
)
replace_once(
    "modules/navigation/workspace_shell.py",
    '''    retail_inventory = (\n        operation_mode != PRODUCTION_OPERATION\n        and str(state.get("workspace_mode") or "") == BUYER_WORKSPACE\n        and str(state.get("buyer_section") or "") == INVENTORY_DASHBOARD_SECTION\n    )\n    production_inventory = operation_mode == PRODUCTION_OPERATION and category == "Inventory"\n    if category == "Inventory" and (retail_inventory or production_inventory):\n''',
    '''    retail_inventory = (\n        operation_mode != PRODUCTION_OPERATION\n        and category == "Inventory"\n        and state.get("flat_virtual_surface") == INVENTORY_COMMAND_CENTER_SURFACE\n    )\n    production_inventory = operation_mode == PRODUCTION_OPERATION and category == "Inventory"\n    if category == "Inventory" and (retail_inventory or production_inventory):\n''',
)

# modules/navigation/role_home.py
replace_once(
    "modules/navigation/role_home.py",
    '    HOME_WORKSPACE,\n    INVENTORY_COUNTS_SECTION,\n',
    '    HOME_WORKSPACE,\n    INVENTORY_COMMAND_CENTER_SURFACE,\n    INVENTORY_COUNTS_SECTION,\n',
)
replace_once(
    "modules/navigation/role_home.py",
    '    HomeAction("Review inventory", "Stock health, reorders, and aging risk.", RETAIL_OPS, BUYER_WORKSPACE, "📊 Inventory Dashboard", ("dev", "admin", "buyer", "read_only")),\n',
    '    HomeAction("Review inventory", "Search stock, packages, status, receiving, and inventory actions.", roles=("dev", "admin", "buyer", "read_only"), intent="inventory_command_center"),\n',
)
replace_once(
    "modules/navigation/role_home.py",
    '    HomeAction("Build purchasing decisions", "Recommendations, budget, deliveries, and POs.", RETAIL_OPS, BUYER_WORKSPACE, "🧾 PO Builder", ("dev", "admin", "buyer")),\n',
    '    HomeAction("Build purchasing decisions", "Buyer overview, recommendations, budget, deliveries, and POs.", RETAIL_OPS, BUYER_WORKSPACE, "📊 Inventory Dashboard", ("dev", "admin", "buyer")),\n',
)
replace_once(
    "modules/navigation/role_home.py",
    '''def activate_home_action(state: MutableMapping[str, Any], action: HomeAction) -> None:\n    if action.intent == "package_studio":\n        state["package_studio_open"] = True\n        return\n''',
    '''def activate_home_action(state: MutableMapping[str, Any], action: HomeAction) -> None:\n    if action.intent == "package_studio":\n        state["package_studio_open"] = True\n        return\n    if action.intent == "inventory_command_center":\n        state["operations_group"] = RETAIL_OPS\n        state["workspace_mode"] = BUYER_WORKSPACE\n        state["flat_navigation_section"] = "Inventory"\n        state["mobile_flat_navigation_section"] = "Inventory"\n        state["flat_virtual_surface"] = INVENTORY_COMMAND_CENTER_SURFACE\n        return\n''',
)
