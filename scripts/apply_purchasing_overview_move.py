from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Keep the legacy route key so app.py remains untouched. In flat navigation the
# same route is shown as operational Inventory when Inventory is active, and as
# the graph-heavy buyer Overview when Purchasing is active.
replace_once(
    "services/workspace_navigation.py",
    '    "📊 Inventory Dashboard": "Inventory Overview",\n',
    '    "📊 Inventory Dashboard": "Inventory",\n',
)

# Purchasing should land on the existing buyer analytics dashboard instead of
# PO Builder. Inventory continues to use the same route key and is intercepted
# by Inventory v2 only while the Inventory category is active.
replace_once(
    "modules/navigation/workspace_shell.py",
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        workspace = _production_workspace(workspaces)\n        if workspace:\n            _set_production_route(state, workspace)\n        return\n\n    if category in {"Inventory", "Purchasing", "Reports", "Compliance"} and BUYER_WORKSPACE in workspaces:\n''',
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        workspace = _production_workspace(workspaces)\n        if workspace:\n            _set_production_route(state, workspace)\n        return\n\n    if category == "Purchasing" and BUYER_WORKSPACE in workspaces:\n        _set_buyer_route(state, INVENTORY_DASHBOARD_SECTION, section_groups)\n        return\n\n    if category in {"Inventory", "Reports", "Compliance"} and BUYER_WORKSPACE in workspaces:\n''',
)

replace_once(
    "modules/navigation/workspace_shell.py",
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        return []\n    if category in {"Inventory", "Purchasing", "Reports", "Compliance"}:\n        return [\n            (buyer_section_display_name(section), "section", section)\n            for section in flat_buyer_sections(category, dict(section_groups))\n        ]\n''',
    '''    if category == "Inventory" and operation_mode == PRODUCTION_OPERATION:\n        return []\n    if category == "Purchasing":\n        return [("Overview", "section", INVENTORY_DASHBOARD_SECTION)] + [\n            (buyer_section_display_name(section), "section", section)\n            for section in flat_buyer_sections(category, dict(section_groups))\n        ]\n    if category in {"Inventory", "Reports", "Compliance"}:\n        return [\n            (buyer_section_display_name(section), "section", section)\n            for section in flat_buyer_sections(category, dict(section_groups))\n        ]\n''',
)

replace_once(
    "modules/navigation/workspace_shell.py",
    '''    if (\n        operation_mode == PRODUCTION_OPERATION\n        and requested_category == "Inventory"\n        and "Inventory" in available\n    ):\n        inferred = "Inventory"\n        _default_route_for_category(state, "Inventory", groups, section_groups)\n    elif requested_category == "Data & Settings" and state.get("flat_virtual_surface") == LOCATION_SETTINGS_SURFACE:\n''',
    '''    if (\n        operation_mode == PRODUCTION_OPERATION\n        and requested_category == "Inventory"\n        and "Inventory" in available\n    ):\n        inferred = "Inventory"\n        _default_route_for_category(state, "Inventory", groups, section_groups)\n    elif (\n        operation_mode != PRODUCTION_OPERATION\n        and requested_category == "Purchasing"\n        and str(state.get("workspace_mode") or "") == BUYER_WORKSPACE\n        and str(state.get("buyer_section") or "") == INVENTORY_DASHBOARD_SECTION\n        and "Purchasing" in available\n    ):\n        inferred = "Purchasing"\n    elif requested_category == "Data & Settings" and state.get("flat_virtual_surface") == LOCATION_SETTINGS_SURFACE:\n''',
)
