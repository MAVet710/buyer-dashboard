from pathlib import Path

from modules.navigation.workspace_shell import (
    INVENTORY_DASHBOARD_SECTION,
    _current_secondary_label,
    _default_route_for_category,
    _secondary_choices,
)
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    RETAIL_OPS,
    buyer_section_display_name,
    buyer_section_groups,
    flat_buyer_sections,
    flat_category_for_route,
)


def _groups():
    return {RETAIL_OPS: [BUYER_WORKSPACE]}


def _sections():
    return buyer_section_groups(
        is_admin=False,
        user_role="buyer",
        admin_exports_enabled=True,
    )


def test_purchasing_defaults_to_existing_buyer_analytics_dashboard():
    state = {"active_operation_mode": "Retail Ops"}
    _default_route_for_category(state, "Purchasing", _groups(), _sections())

    assert state["workspace_mode"] == BUYER_WORKSPACE
    assert state["buyer_section"] == INVENTORY_DASHBOARD_SECTION


def test_purchasing_secondary_navigation_starts_with_overview():
    choices = _secondary_choices(
        "Purchasing",
        _groups(),
        _sections(),
        operation_mode="Retail Ops",
    )

    assert choices[0] == ("Overview", "section", INVENTORY_DASHBOARD_SECTION)
    labels = [label for label, _, _ in choices]
    assert "Buying Recommendations" in labels
    assert "Delivery Performance" in labels
    assert "Purchase Orders" in labels
    assert "Buying Budget" in labels


def test_purchasing_overview_route_selects_overview_label():
    state = {
        "workspace_mode": BUYER_WORKSPACE,
        "buyer_section": INVENTORY_DASHBOARD_SECTION,
    }
    choices = _secondary_choices(
        "Purchasing",
        _groups(),
        _sections(),
        operation_mode="Retail Ops",
    )
    assert _current_secondary_label(state, choices) == "Overview"


def test_inventory_keeps_operational_inventory_route_compatibility():
    state = {"active_operation_mode": "Retail Ops"}
    _default_route_for_category(state, "Inventory", _groups(), _sections())

    assert state["workspace_mode"] == BUYER_WORKSPACE
    assert state["buyer_section"] == INVENTORY_DASHBOARD_SECTION
    assert flat_category_for_route(BUYER_WORKSPACE, INVENTORY_DASHBOARD_SECTION) == "Inventory"
    assert buyer_section_display_name(INVENTORY_DASHBOARD_SECTION) == "Inventory"


def test_inventory_and_purchasing_keep_distinct_secondary_surfaces():
    inventory_labels = [
        label
        for label, _, _ in _secondary_choices(
            "Inventory",
            _groups(),
            _sections(),
            operation_mode="Retail Ops",
        )
    ]
    purchasing_labels = [
        label
        for label, _, _ in _secondary_choices(
            "Purchasing",
            _groups(),
            _sections(),
            operation_mode="Retail Ops",
        )
    ]

    assert inventory_labels[0] == "Inventory"
    assert "Inventory Audits" in inventory_labels
    assert "Overview" not in inventory_labels
    assert purchasing_labels[0] == "Overview"
    assert "Inventory Audits" not in purchasing_labels
    assert INVENTORY_DASHBOARD_SECTION not in flat_buyer_sections("Purchasing", _sections())


def test_shell_only_intercepts_dashboard_route_when_inventory_category_is_active():
    source = Path("modules/navigation/workspace_shell.py").read_text(encoding="utf-8")
    assert 'requested_category == "Purchasing"' in source
    assert 'str(state.get("buyer_section") or "") == INVENTORY_DASHBOARD_SECTION' in source
    assert 'if category == "Inventory" and (retail_inventory or production_inventory):' in source
