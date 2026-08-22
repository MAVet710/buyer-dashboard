"""Role- and license-aware workspace navigation configuration."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping, Sequence
from typing import Any


BUYER_WORKSPACE = "🛒 Buyer Operations"
HOME_WORKSPACE = "Operations Home"
WHITE_LABEL_WORKSPACE = "🏷️ White Label / Repack"
COMAN_WORKSPACE = "🏭 Co-Man Production"
EXTRACTION_WORKSPACE = "🧪 Extraction Command Center"
COMMERCIAL_WORKSPACE = "📦 Orders & Fulfillment"
DATA_HUB_WORKSPACE = "📥 Data Hub"
ANALYTICS_WORKSPACE = "📊 Profitability Analytics"
RETAIL_OPS = "🛍️ Retail Ops"
HOME_OPS = "Home"
PRODUCTION_OPS = "🏭 Production Ops"
COMMERCIAL_OPS = "🤝 Commercial Ops"
DATA_OPERATIONS = "🗂️ Data & Integrations"
AI_INTEGRATIONS_SECTION = "🧠 AI & METRC Integrations"
METRC_INTEGRATIONS_SECTION = "🔗 METRC Integrations"
INVENTORY_COUNTS_SECTION = "📋 Inventory Counts"
MA_FLOWER_EQUIVALENCY_SECTION = "🌿 MA Flower Equivalency"

# The flat shell is presentation-only. Every entry resolves to the same legacy
# route identifiers used by the existing application, so pages and permissions
# remain backwards compatible.
FLAT_NAV_ORDER = (
    "Home",
    "Inventory",
    "Purchasing",
    "Orders",
    "Production",
    "Reports",
    "Compliance",
    "Data & Settings",
)

BUYER_SECTION_FLAT_CATEGORY = {
    "📊 Inventory Dashboard": "Inventory",
    INVENTORY_COUNTS_SECTION: "Inventory",
    "🐢 Slow Movers": "Inventory",
    MA_FLOWER_EQUIVALENCY_SECTION: "Inventory",
    "🧠 Buyer Intelligence": "Purchasing",
    "🚚 Delivery Impact": "Purchasing",
    "🧾 PO Builder": "Purchasing",
    "💰 Purchasing Budget": "Purchasing",
    "📈 Trends": "Reports",
    "🧭 Compliance Q&A": "Compliance",
    "🏷️ Nomenclature Mapper": "Compliance",
    "🛠️ Admin Tools": "Data & Settings",
    AI_INTEGRATIONS_SECTION: "Data & Settings",
    METRC_INTEGRATIONS_SECTION: "Data & Settings",
}

BUYER_SECTION_DISPLAY_NAME = {
    "📊 Inventory Dashboard": "Inventory",
    INVENTORY_COUNTS_SECTION: "Inventory Audits",
    "🐢 Slow Movers": "Slow Movers",
    MA_FLOWER_EQUIVALENCY_SECTION: "MA Flower Equivalency",
    "🧠 Buyer Intelligence": "Buying Recommendations",
    "🚚 Delivery Impact": "Delivery Performance",
    "🧾 PO Builder": "Purchase Orders",
    "💰 Purchasing Budget": "Buying Budget",
    "📈 Trends": "Sales & Category Trends",
    "🧭 Compliance Q&A": "Compliance Q&A",
    "🏷️ Nomenclature Mapper": "Product Name Mapper",
    "🛠️ Admin Tools": "Admin Tools",
    AI_INTEGRATIONS_SECTION: "AI & METRC Integrations",
    METRC_INTEGRATIONS_SECTION: "METRC Integrations",
}

PENDING_NAVIGATION_KEY = "_pending_workspace_navigation"


def queue_workspace_navigation(
    state: MutableMapping[str, Any],
    *,
    group: str,
    workspace: str,
    buyer_section: str = "",
) -> None:
    """Queue navigation for the next rerun without mutating live widget keys."""

    state[PENDING_NAVIGATION_KEY] = {
        "group": str(group),
        "workspace": str(workspace),
        "buyer_section": str(buyer_section or ""),
    }


def apply_pending_workspace_navigation(state: MutableMapping[str, Any]) -> bool:
    """Apply and clear one queued request before navigation widgets render."""

    pending = state.pop(PENDING_NAVIGATION_KEY, None)
    if not isinstance(pending, dict):
        return False
    group = str(pending.get("group") or "")
    workspace = str(pending.get("workspace") or "")
    if not group or not workspace:
        return False
    state["operations_group"] = group
    state["workspace_mode"] = workspace
    buyer_section = str(pending.get("buyer_section") or "")
    if buyer_section:
        state["buyer_section"] = buyer_section
    return True


def can_manage_ai_integrations(user_role: str | None) -> bool:
    """Return whether a role may view or change platform AI credentials."""
    return str(user_role or "").strip().lower() == "dev"


def workspace_groups(feature_enabled: Callable[..., bool]) -> dict[str, list[str]]:
    """Return licensed workspaces grouped by the operation they support."""
    groups = {
        HOME_OPS: [HOME_WORKSPACE],
        RETAIL_OPS: [],
        PRODUCTION_OPS: [],
        COMMERCIAL_OPS: [],
        DATA_OPERATIONS: [],
    }
    if feature_enabled("buyer_module", default_enabled=True):
        groups[RETAIL_OPS].extend([BUYER_WORKSPACE, WHITE_LABEL_WORKSPACE])
        groups[PRODUCTION_OPS].append(COMAN_WORKSPACE)
        groups[COMMERCIAL_OPS].append(COMMERCIAL_WORKSPACE)
    if feature_enabled("extraction_module", default_enabled=True):
        groups[PRODUCTION_OPS].append(EXTRACTION_WORKSPACE)
        if COMMERCIAL_WORKSPACE not in groups[COMMERCIAL_OPS]:
            groups[COMMERCIAL_OPS].append(COMMERCIAL_WORKSPACE)
    if groups[RETAIL_OPS] or groups[PRODUCTION_OPS]:
        groups[DATA_OPERATIONS].extend([DATA_HUB_WORKSPACE, ANALYTICS_WORKSPACE])
    return {group: options for group, options in groups.items() if options}


def workspace_options(feature_enabled: Callable[..., bool]) -> list[str]:
    """Return the legacy flat list in the same order as the grouped navigator."""
    return [
        workspace
        for options in workspace_groups(feature_enabled).values()
        for workspace in options
    ]


def workspace_group(workspace: str) -> str | None:
    """Resolve a saved workspace to its top-level operations group."""
    if workspace == HOME_WORKSPACE:
        return HOME_OPS
    if workspace in {BUYER_WORKSPACE, WHITE_LABEL_WORKSPACE}:
        return RETAIL_OPS
    if workspace in {COMAN_WORKSPACE, EXTRACTION_WORKSPACE}:
        return PRODUCTION_OPS
    if workspace == COMMERCIAL_WORKSPACE:
        return COMMERCIAL_OPS
    if workspace in {DATA_HUB_WORKSPACE, ANALYTICS_WORKSPACE}:
        return DATA_OPERATIONS
    return None


def flat_category_for_route(workspace: str, buyer_section: str = "") -> str:
    """Resolve an existing workspace/page route to its user-facing flat category."""
    if workspace == HOME_WORKSPACE:
        return "Home"
    if workspace == BUYER_WORKSPACE:
        return BUYER_SECTION_FLAT_CATEGORY.get(str(buyer_section or ""), "Inventory")
    if workspace == COMMERCIAL_WORKSPACE:
        return "Orders"
    if workspace in {COMAN_WORKSPACE, EXTRACTION_WORKSPACE, WHITE_LABEL_WORKSPACE}:
        return "Production"
    if workspace == DATA_HUB_WORKSPACE:
        return "Data & Settings"
    return "Home"


def flat_buyer_sections(
    category: str,
    section_groups: dict[str, Sequence[str]],
) -> list[str]:
    """Return allowed Buyer pages for one flat navigation category."""
    allowed = [section for sections in section_groups.values() for section in sections]
    return [
        section
        for section in allowed
        if BUYER_SECTION_FLAT_CATEGORY.get(section) == str(category)
    ]


def buyer_section_display_name(section: str) -> str:
    """Return plain-language navigation text without changing the legacy route key."""
    return BUYER_SECTION_DISPLAY_NAME.get(str(section), str(section))


def flat_navigation_parity(
    section_groups: dict[str, Sequence[str]],
) -> tuple[bool, tuple[str, ...]]:
    """Verify every role-visible Buyer page has a flat-shell home."""
    visible = [section for sections in section_groups.values() for section in sections]
    missing = tuple(section for section in visible if section not in BUYER_SECTION_FLAT_CATEGORY)
    return not missing, missing


def buyer_section_options(
    *,
    is_admin: bool,
    user_role: str | None = None,
    admin_exports_enabled: bool = True,
) -> list[str]:
    """Return role-safe Buyer Operations pages.

    AI configuration is platform infrastructure and is therefore visible only
    to Level DEV. Every other durable account receives a METRC-only page.
    """
    return [
        section
        for sections in buyer_section_groups(
            is_admin=is_admin,
            user_role=user_role,
            admin_exports_enabled=admin_exports_enabled,
        ).values()
        for section in sections
    ]


def buyer_section_groups(
    *,
    is_admin: bool,
    user_role: str | None = None,
    admin_exports_enabled: bool = True,
) -> dict[str, list[str]]:
    """Return Buyer Operations pages grouped around common retail tasks.

    The compact groups keep the sidebar scannable while preserving every
    existing page and its role restrictions.
    """
    groups = {
        "Overview": [
            "📊 Inventory Dashboard",
            "📈 Trends",
            "🧠 Buyer Intelligence",
        ],
        "Inventory": [
            INVENTORY_COUNTS_SECTION,
            "🐢 Slow Movers",
            MA_FLOWER_EQUIVALENCY_SECTION,
        ],
        "Purchasing": [
            "🚚 Delivery Impact",
            "🧾 PO Builder",
            "💰 Purchasing Budget",
        ],
        "Compliance": [
            "🧭 Compliance Q&A",
            "🏷️ Nomenclature Mapper",
        ],
        "Administration": [],
    }
    if is_admin and admin_exports_enabled:
        groups["Administration"].append("🛠️ Admin Tools")
    normalized_role = str(user_role or ("admin" if is_admin else "buyer")).strip().lower()
    groups["Administration"].append(
        AI_INTEGRATIONS_SECTION
        if can_manage_ai_integrations(normalized_role)
        else METRC_INTEGRATIONS_SECTION
    )
    return {group: sections for group, sections in groups.items() if sections}
