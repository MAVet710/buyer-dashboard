"""Role- and license-aware workspace navigation configuration."""

from __future__ import annotations

from collections.abc import Callable


BUYER_WORKSPACE = "🛒 Buyer Operations"
WHITE_LABEL_WORKSPACE = "🏷️ White Label / Repack"
COMAN_WORKSPACE = "🏭 Co-Man Production"
EXTRACTION_WORKSPACE = "🧪 Extraction Command Center"
COMMERCIAL_WORKSPACE = "📦 Orders & Fulfillment"
DATA_HUB_WORKSPACE = "📥 Data Hub"
RETAIL_OPS = "🛍️ Retail Ops"
PRODUCTION_OPS = "🏭 Production Ops"
COMMERCIAL_OPS = "🤝 Commercial Ops"
DATA_OPERATIONS = "🗂️ Data & Integrations"


def workspace_groups(feature_enabled: Callable[..., bool]) -> dict[str, list[str]]:
    """Return licensed workspaces grouped by the operation they support."""
    groups = {
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
    if workspace in {BUYER_WORKSPACE, WHITE_LABEL_WORKSPACE}:
        return RETAIL_OPS
    if workspace in {COMAN_WORKSPACE, EXTRACTION_WORKSPACE}:
        return PRODUCTION_OPS
    if workspace == COMMERCIAL_WORKSPACE:
        return COMMERCIAL_OPS
    if workspace == DATA_HUB_WORKSPACE:
        return DATA_OPERATIONS
    return None


def buyer_section_options(*, is_admin: bool, admin_exports_enabled: bool = True) -> list[str]:
    options = [
        "📊 Inventory Dashboard",
        "📈 Trends",
        "🚚 Delivery Impact",
        "🐢 Slow Movers",
        "🧾 PO Builder",
        "🧭 Compliance Q&A",
        "🧠 Buyer Intelligence",
        "🏷️ Nomenclature Mapper",
        "💰 Purchasing Budget",
    ]
    if is_admin and admin_exports_enabled:
        options.append("🛠️ Admin Tools")
    if is_admin:
        options.append("🔌 Integrations")
    return options
