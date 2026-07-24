"""Role- and license-aware workspace navigation configuration."""

from __future__ import annotations

from collections.abc import Callable


BUYER_WORKSPACE = "🛒 Buyer Operations"
WHITE_LABEL_WORKSPACE = "🏷️ White Label / Repack"
COMAN_WORKSPACE = "🏭 Co-Man Production"
EXTRACTION_WORKSPACE = "🧪 Extraction Command Center"


def workspace_options(feature_enabled: Callable[..., bool]) -> list[str]:
    options: list[str] = []
    if feature_enabled("buyer_module", default_enabled=True):
        options.extend([BUYER_WORKSPACE, WHITE_LABEL_WORKSPACE, COMAN_WORKSPACE])
    if feature_enabled("extraction_module", default_enabled=True):
        options.append(EXTRACTION_WORKSPACE)
    return options


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
