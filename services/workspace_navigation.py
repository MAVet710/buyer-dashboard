"""Role- and license-aware workspace navigation configuration."""

from __future__ import annotations

from collections.abc import Callable


BUYER_WORKSPACE = "🛒 Buyer Operations"
HOME_WORKSPACE = "Operations Home"
WHITE_LABEL_WORKSPACE = "🏷️ White Label / Repack"
COMAN_WORKSPACE = "🏭 Co-Man Production"
EXTRACTION_WORKSPACE = "🧪 Extraction Command Center"
COMMERCIAL_WORKSPACE = "📦 Orders & Fulfillment"
DATA_HUB_WORKSPACE = "📥 Data Hub"
RETAIL_OPS = "🛍️ Retail Ops"
HOME_OPS = "Home"
PRODUCTION_OPS = "🏭 Production Ops"
COMMERCIAL_OPS = "🤝 Commercial Ops"
DATA_OPERATIONS = "🗂️ Data & Integrations"
AI_INTEGRATIONS_SECTION = "🧠 AI & METRC Integrations"
METRC_INTEGRATIONS_SECTION = "🔗 METRC Integrations"
INVENTORY_COUNTS_SECTION = "📋 Inventory Counts"
MA_FLOWER_EQUIVALENCY_SECTION = "🌿 MA Flower Equivalency"


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
        groups[DATA_OPERATIONS].append(DATA_HUB_WORKSPACE)
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
    if workspace == DATA_HUB_WORKSPACE:
        return DATA_OPERATIONS
    return None


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
